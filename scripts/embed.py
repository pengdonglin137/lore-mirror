#!/usr/bin/env python3
"""
Generate semantic embeddings for mailing list messages and build FAISS indexes.

Usage:
    python3 scripts/embed.py                    # embed all enabled inboxes
    python3 scripts/embed.py --inbox netdev     # embed specific inbox
    python3 scripts/embed.py --rebuild          # force full rebuild
    python3 scripts/embed.py --stats            # show embedding statistics
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_utils import load_config
from scripts.database import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("embed")

# Module-level model singleton
_model = None


def get_model(model_name: str = "all-MiniLM-L6-v2"):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        log.info(f"Loading embedding model: {model_name}")
        _model = SentenceTransformer(model_name)
        log.info(f"Model loaded (dim={_model.get_sentence_embedding_dimension()})")
    return _model


def prepare_text(subject: str, body_text: str | None, is_patch: bool, max_words: int, patch_words: int) -> str:
    """Prepare text for embedding: subject + truncated body."""
    parts = [subject or ""]
    if body_text:
        words = body_text.split()
        limit = patch_words if is_patch else max_words
        if len(words) > limit:
            parts.append(" ".join(words[:limit]))
        else:
            parts.append(body_text)
    text = "\n".join(parts)
    # Collapse excessive whitespace
    text = " ".join(text.split())
    return text


def get_progress(inbox_name: str, db_dir: str) -> dict:
    """Read embedding progress from metadata file."""
    meta_path = Path(db_dir) / f"{inbox_name}.embed_meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return {"last_embedded_id": 0, "vector_count": 0}


def save_progress(inbox_name: str, db_dir: str, last_id: int, count: int):
    """Save embedding progress to metadata file."""
    meta_path = Path(db_dir) / f"{inbox_name}.embed_meta.json"
    with open(meta_path, "w") as f:
        json.dump({"last_embedded_id": last_id, "vector_count": count}, f)


def build_index(vectors: np.ndarray, nlist: int, nprobe: int):
    """Build FAISS index from vectors. Uses cosine similarity (inner product on normalized vectors)."""
    import faiss

    dim = vectors.shape[1]
    n = vectors.shape[0]

    if n < 500_000 or nlist == 0:
        log.info(f"Building IndexFlatIP ({n} vectors, dim={dim})")
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
    else:
        nlist_actual = min(nlist, n // 10)  # need at least 10x vectors vs clusters
        log.info(f"Building IndexIVFFlat ({n} vectors, {nlist_actual} clusters)")
        quantizer = faiss.IndexFlatIP(dim)
        index = faiss.IndexIVFFlat(quantizer, dim, nlist_actual)
        index.nprobe = nprobe
        index.train(vectors)
        index.add(vectors)

    return index


def embed_inbox(inbox_name: str, config: dict, rebuild: bool = False) -> dict:
    """Embed all messages in an inbox and build/update FAISS index.

    Returns dict with stats: new_vectors, total_vectors, elapsed_seconds.
    """
    import faiss

    db_dir = config["database"]["dir"]
    vs_config = config.get("vector_search", {})
    model_name = vs_config.get("model_name", "all-MiniLM-L6-v2")
    max_body_words = vs_config.get("max_body_words", 400)
    patch_body_words = vs_config.get("patch_body_words", 200)
    batch_size = vs_config.get("batch_size", 256)
    nlist = vs_config.get("nlist", 4096)
    nprobe = vs_config.get("nprobe", 16)

    db_path = Path(db_dir) / f"{inbox_name}.db"
    if not db_path.exists():
        log.warning(f"Database not found: {db_path}")
        return {"new_vectors": 0, "total_vectors": 0, "elapsed_seconds": 0}

    faiss_path = Path(db_dir) / f"{inbox_name}.faiss"
    map_path = Path(db_dir) / f"{inbox_name}.map.npy"

    if rebuild:
        for p in [faiss_path, map_path]:
            if p.exists():
                p.unlink()
        progress = {"last_embedded_id": 0, "vector_count": 0}
    else:
        progress = get_progress(inbox_name, db_dir)

    last_id = progress["last_embedded_id"]
    existing_count = progress["vector_count"]

    conn = get_connection(db_path)

    # Count new messages
    total_new = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE id > ?", (last_id,)
    ).fetchone()[0]

    if total_new == 0:
        log.info(f"[{inbox_name}] No new messages to embed (total vectors: {existing_count})")
        conn.close()
        return {"new_vectors": 0, "total_vectors": existing_count, "elapsed_seconds": 0}

    log.info(f"[{inbox_name}] Embedding {total_new} new messages (existing: {existing_count})")

    model = get_model(model_name)

    # Stream messages in batches
    new_embeddings = []
    new_ids = []
    processed = 0
    t0 = time.time()

    cursor = conn.execute(
        "SELECT id, subject, body_text FROM messages WHERE id > ? ORDER BY id",
        (last_id,),
    )

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        texts = []
        batch_ids = []
        for row in rows:
            subject = row["subject"] or ""
            is_patch = bool(subject and __import__("re").match(r"\[PATCH", subject, __import__("re").IGNORECASE))
            text = prepare_text(subject, row["body_text"], is_patch, max_body_words, patch_body_words)
            texts.append(text)
            batch_ids.append(row["id"])

        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        new_embeddings.append(embeddings)
        new_ids.extend(batch_ids)

        processed += len(rows)
        if processed % 10_000 == 0 or processed == total_new:
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            log.info(f"[{inbox_name}] {processed}/{total_new} ({rate:.0f}/s)")

    cursor.close()
    conn.close()

    if not new_embeddings:
        return {"new_vectors": 0, "total_vectors": existing_count, "elapsed_seconds": time.time() - t0}

    new_vectors = np.vstack(new_embeddings)
    new_ids_array = np.array(new_ids, dtype=np.int64)

    # Merge with existing index if present
    if faiss_path.exists() and not rebuild:
        existing_index = faiss.read_index(str(faiss_path), faiss.IO_FLAG_MMAP)
        existing_map = np.load(str(map_path), mmap_mode="r")
        all_vectors_list = []

        # Reconstruct existing vectors
        for i in range(existing_index.ntotal):
            vec = np.zeros(1, dtype=np.float32)
            existing_index.reconstruct(i, vec.reshape(-1))
            all_vectors_list.append(vec)

        all_vectors_list.append(new_vectors)
        all_vectors = np.vstack(all_vectors_list)
        all_ids = np.concatenate([np.array(existing_map), new_ids_array])
    else:
        all_vectors = new_vectors
        all_ids = new_ids_array

    # Build new index
    index = build_index(all_vectors, nlist, nprobe)

    # Save
    faiss.write_index(index, str(faiss_path))
    np.save(str(map_path), all_ids)
    save_progress(inbox_name, db_dir, int(all_ids[-1]), len(all_ids))

    elapsed = time.time() - t0
    log.info(
        f"[{inbox_name}] Done: {len(new_ids)} new, {len(all_ids)} total, "
        f"{faiss_path.stat().st_size / 1024 / 1024:.1f}MB index, {elapsed:.1f}s"
    )

    return {
        "new_vectors": len(new_ids),
        "total_vectors": len(all_ids),
        "elapsed_seconds": elapsed,
    }


def show_stats(config: dict):
    """Show embedding statistics for all inboxes."""
    db_dir = config["database"]["dir"]
    db_path = Path(db_dir)

    print(f"{'Inbox':<25} {'Messages':>10} {'Vectors':>10} {'Last ID':>10} {'Index Size':>12}")
    print("-" * 72)

    for faiss_file in sorted(db_path.glob("*.faiss")):
        inbox = faiss_file.stem
        meta = get_progress(inbox, db_dir)

        db_file = db_path / f"{inbox}.db"
        msg_count = 0
        if db_file.exists():
            conn = get_connection(db_file)
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            conn.close()

        index_size = faiss_file.stat().st_size / 1024 / 1024
        print(f"{inbox:<25} {msg_count:>10,} {meta['vector_count']:>10,} {meta['last_embedded_id']:>10} {index_size:>10.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="Generate semantic embeddings for mailing list messages")
    parser.add_argument("--inbox", help="Embed specific inbox (default: all enabled)")
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild (ignore progress)")
    parser.add_argument("--stats", action="store_true", help="Show embedding statistics")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config.yaml"), help="Config file path")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    if args.stats:
        show_stats(config)
        return

    vs_config = config.get("vector_search", {})
    if not vs_config.get("enabled", False):
        log.error("Vector search is not enabled in config.yaml")
        sys.exit(1)

    inboxes = []
    if args.inbox:
        inboxes = [args.inbox]
    else:
        inboxes = [ib["name"] for ib in config.get("inboxes", [])]

    total_new = 0
    total_all = 0
    t0 = time.time()

    for inbox_name in inboxes:
        try:
            result = embed_inbox(inbox_name, config, rebuild=args.rebuild)
            total_new += result["new_vectors"]
            total_all += result["total_vectors"]
        except Exception as e:
            log.error(f"[{inbox_name}] Failed: {e}")
            import traceback
            traceback.print_exc()

    elapsed = time.time() - t0
    log.info(f"All done: {total_new} new vectors, {total_all} total, {elapsed:.1f}s")


if __name__ == "__main__":
    main()
