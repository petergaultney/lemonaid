"""The record of which alerts have fired, so restarts don't repeat them."""

import json
from pathlib import Path

from . import paths


def _file() -> Path:
    return paths.usage_dir() / "alerted.json"


def load() -> dict[str, dict]:
    return json.loads(_file().read_text()) if _file().exists() else {}


def save(state: dict[str, dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(_file())
