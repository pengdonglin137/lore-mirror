"""
Vector/semantic search backend using FAISS indexes.

Loaded lazily on first search request. Each inbox's FAISS index is
memory-mapped for fast access without loading everything into RAM.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger("vector_search")

_model = None
_model_lock = threading.Lock()
_indexes: dict = {}
_config: dict | None = None


@dataclass
class InboxIndex:
    name: str
    index: object  # faiss.Index
    id_map: np.ndarray
    vector_count: int
    is_ivf: bool


def set_config(config: dict):
    global _config
    _config = config


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            model_name = (_config or {}).get("vector_search", {}).get("model_name", "all-MiniLM-L6-v2")
            log.info(f"Loading embedding model: {model_name}")
            _model = SentenceTransformer(model_name)
            log.info("Embedding model loaded")
        return _model


def _load_inbox_index(inbox_name: str) -> InboxIndex | None:
    if inbox_name in _indexes:
        return _indexes[inbox_name]

    import faiss

    db_dir = (_config or {}).get("database", {}).get("dir", "db")
    faiss_path = Path(db_dir) / f"{inbox_name}.faiss"
    map_path = Path(db_dir) / f"{inbox_name}.map.npy"

    if not faiss_path.exists() or not map_path.exists():
        return None

    try:
        index = faiss.read_index(str(faiss_path), faiss.IO_FLAG_MMAP)
        id_map = np.load(str(map_path), mmap_mode="r")
        is_ivf = hasattr(index, "nprobe")

        if is_ivf:
            nprobe = (_config or {}).get("vector_search", {}).get("nprobe", 16)
            index.nprobe = nprobe

        info = InboxIndex(
            name=inbox_name,
            index=index,
            id_map=id_map,
            vector_count=index.ntotal,
            is_ivf=is_ivf,
        )
        _indexes[inbox_name] = info
        log.info(f"Loaded FAISS index for {inbox_name}: {index.ntotal} vectors")
        return info
    except Exception as e:
        log.error(f"Failed to load FAISS index for {inbox_name}: {e}")
        return None


def get_available_vector_inboxes() -> list[str]:
    """Scan db/ for .faiss files, return inbox names."""
    db_dir = (_config or {}).get("database", {}).get("dir", "db")
    return sorted(p.stem for p in Path(db_dir).glob("*.faiss"))


def semantic_search(query: str, inbox: str | None = None, top_k: int = 50) -> list[dict]:
    """Search by semantic similarity. Returns [{inbox_name, message_id, score}]."""
    model = _get_model()

    # Encode query
    query_vec = model.encode([query], normalize_embeddings=True)[0]

    # Determine inboxes to search
    if inbox:
        inboxes = [inbox]
    else:
        inboxes = get_available_vector_inboxes()

    if not inboxes:
        return []

    # Search each inbox
    all_results = []
    for ib_name in inboxes:
        info = _load_inbox_index(ib_name)
        if info is None or info.vector_count == 0:
            continue

        k = min(top_k, info.vector_count)
        scores, indices = info.index.search(query_vec.reshape(1, -1).astype(np.float32), k)

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            msg_id = int(info.id_map[idx])
            all_results.append({
                "inbox_name": ib_name,
                "message_id": msg_id,
                "score": float(score),
            })

    # Sort by score descending, take top_k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


def unload_all():
    """Release all loaded indexes and model."""
    global _model, _indexes
    _indexes.clear()
    _model = None
