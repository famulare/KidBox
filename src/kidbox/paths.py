from __future__ import annotations

from pathlib import Path
from typing import Dict, Any


def get_data_root(config: Dict[str, Any]) -> Path:
    root = config.get("data_root", "/data/kidbox")
    return Path(root).expanduser().resolve()


def ensure_directories(data_root: Path) -> Dict[str, Path]:
    paint_dir = data_root / "paint"
    photos_dir = data_root / "photos"
    typing_dir = data_root / "typing"

    paint_dir.mkdir(parents=True, exist_ok=True)
    (photos_dir / "library").mkdir(parents=True, exist_ok=True)
    (photos_dir / "thumbs").mkdir(parents=True, exist_ok=True)
    typing_dir.mkdir(parents=True, exist_ok=True)

    return {
        "paint": paint_dir,
        "photos": photos_dir,
        "typing": typing_dir,
    }
