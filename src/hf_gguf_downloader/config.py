from __future__ import annotations

import json
import os
from pathlib import Path

_APP_DIR_NAME = "HFGGUFDownloader"


def load_download_directory() -> str:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    directory = data.get("download_directory", "")
    return directory if isinstance(directory, str) else ""


def save_download_directory(directory: str) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"download_directory": directory}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / _APP_DIR_NAME / "config.json"
