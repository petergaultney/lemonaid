"""The `[po-box]` table: the shared folder that holds PO boxes, and whose lemons this machine registers."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PoBoxConfig:
    root: Path | None = None  # None: no PO boxes on this machine
    owner: str = ""
    keep_read_days: int = 7


def _warn(key: str, expected: str) -> None:
    print(f"Warning: [po-box] {key} must be {expected}", file=sys.stderr)


def _root(raw: object) -> Path | None:
    if raw is None or raw == "":
        return None

    if not isinstance(raw, str):
        _warn("root", "a folder path")
        return None

    return Path(raw).expanduser()


def _safe(name: str) -> bool:
    return bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name


def _owner(raw: object) -> str:
    if raw is None:
        user = os.environ.get("USER", "")
        return user if _safe(user) else ""

    if not isinstance(raw, str) or not _safe(raw):
        _warn("owner", "a name that is safe as one folder name")
        return ""

    return raw


def _keep(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        _warn("keep_read_days", "a whole number of at least 1")
        return PoBoxConfig.keep_read_days

    return raw


def parse(data: dict) -> PoBoxConfig:
    return PoBoxConfig(
        root=_root(data.get("root")),
        owner=_owner(data.get("owner")),
        keep_read_days=_keep(data.get("keep_read_days", PoBoxConfig.keep_read_days)),
    )
