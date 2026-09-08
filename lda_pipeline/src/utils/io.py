"""
I/O and serialization utilities for the LDA topic modeling pipeline.
"""
import os
import json
import pickle
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("nepal_lda")


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with the given name."""
    return logging.getLogger(f"nepal_lda.{name}")


def ensure_dir(path: Union[str, Path]) -> Path:
    """Ensure that the directory for the given path exists."""
    p = Path(path)
    if p.suffix:  # It's a file path
        p.parent.mkdir(parents=True, exist_ok=True)
    else:
        p.mkdir(parents=True, exist_ok=True)
    return p


def load_config(config_path: Union[str, Path] = "config/config.yaml") -> Dict[str, Any]:
    """Load configuration from a YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file.resolve()}")
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def save_json(data: Any, filepath: Union[str, Path], indent: int = 2) -> None:
    """Save serializable data to a JSON file."""
    p = ensure_dir(filepath)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str)
    logger.info(f"Saved JSON to: {p}")


def load_json(filepath: Union[str, Path]) -> Any:
    """Load data from a JSON file."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"JSON file not found: {p.resolve()}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pickle(obj: Any, filepath: Union[str, Path]) -> None:
    """Save an object to a pickle file."""
    p = ensure_dir(filepath)
    with open(p, "wb") as f:
        pickle.dump(obj, f)
    logger.info(f"Saved pickle to: {p}")


def load_pickle(filepath: Union[str, Path]) -> Any:
    """Load an object from a pickle file."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"Pickle file not found: {p.resolve()}")
    with open(p, "rb") as f:
        return pickle.load(f)
