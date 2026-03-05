"""Shared config loading with relative path resolution."""

from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


def load_config(config_path: Path = DEFAULT_CONFIG) -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve relative paths against project root
    repos_dir = Path(config["mirror"]["repos_dir"])
    if not repos_dir.is_absolute():
        config["mirror"]["repos_dir"] = str(PROJECT_ROOT / repos_dir)

    db_dir = Path(config["database"]["dir"])
    if not db_dir.is_absolute():
        config["database"]["dir"] = str(PROJECT_ROOT / db_dir)

    return config
