"""Persistent tracebacks for CLI and TUI failures."""

import importlib.metadata
import os
import sys
import time
import traceback
from pathlib import Path

from .log import get_logger

_log = get_logger("errors")


def record(error: BaseException, context: str) -> None:
    try:
        version = importlib.metadata.version("lemonaid-inbox")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    path = (
        Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
        / "logs"
        / "errors.log"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as output:
            output.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {context}\n")
            output.write(f"lemonaid {version}; Python {sys.version}\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=output)
            output.write("\n")
    except OSError:
        _log.exception("could not write crash traceback to %s", path)
