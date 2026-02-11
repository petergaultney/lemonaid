"""Shared logging for lemonaid.

All components log to /tmp/lemonaid.log via Python's logging module.
Filter with grep: grep 'lemonaid.claude' /tmp/lemonaid.log
"""

import logging
from pathlib import Path

_LOG_PATH = Path("/tmp/lemonaid.log")

_handler = logging.FileHandler(_LOG_PATH)
_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S"))

_root = logging.getLogger("lemonaid")
_root.addHandler(_handler)
_root.setLevel(logging.DEBUG)
# don't propagate to root logger (avoids duplicate output if someone
# configures the root logger elsewhere)
_root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return _root.getChild(name)
