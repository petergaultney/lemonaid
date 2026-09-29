"""Change detection for a set of watched paths, independent of how events are delivered.

A file's fingerprint is its content hash; a directory's is the size and mtime of each
non-hidden regular file directly in it, so a new, removed, or rewritten file changes it but
a lock file or a subdirectory does not. What was last reported is kept per (paths, signer)
in a state directory, so a rearmed waiter reports what changed while none ran; the first
waiter for a set of paths takes the current state as its baseline.
"""

import dataclasses
import hashlib
import json
import pathlib
import tempfile
import time
import typing as ty
from collections import abc

Fingerprint = str | dict[str, str] | None  # file hash, directory listing, or absent


def default_state_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / "lemonaid-watch-file"


def state_stem(state_dir: pathlib.Path, paths: abc.Iterable[pathlib.Path], me: str) -> pathlib.Path:
    key = "\0".join(sorted(str(p.resolve()) for p in paths)) + f"\0\0{me}"
    return state_dir / hashlib.sha1(key.encode()).hexdigest()[:16]


def _entry(entry: pathlib.Path) -> str:
    """ "" for anything but a regular file, including one removed since the listing."""
    try:
        st = entry.stat()
    except FileNotFoundError:
        return ""
    return f"{st.st_size}:{st.st_mtime_ns}" if entry.is_file() else ""


def _fingerprint(path: pathlib.Path) -> Fingerprint:
    try:
        if path.is_dir():
            listing = {e.name: _entry(e) for e in path.iterdir() if not e.name.startswith(".")}
            return {name: fp for name, fp in listing.items() if fp}

        return hashlib.sha1(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _names(label: str, names: abc.Sequence[str]) -> list[str]:
    if not names:
        return []

    more = f" and {len(names) - 3} more" if len(names) > 3 else ""
    return [f"{label} {', '.join(names[:3])}{more}"]


def _describe(path: str, old: Fingerprint, new: Fingerprint) -> str:
    if new is None:
        return f"{path} was removed"

    if old is None:
        return f"{path} was created"

    if isinstance(old, dict) and isinstance(new, dict):
        parts = [
            *_names("added", sorted(set(new) - set(old))),
            *_names("removed", sorted(set(old) - set(new))),
            *_names("changed", sorted(n for n in set(old) & set(new) if old[n] != new[n])),
        ]
        return f"{path}: {'; '.join(parts)}"

    return f"{path} changed"


@dataclasses.dataclass
class FileWatch:
    paths: list[pathlib.Path]
    quiet: float
    reported_path: pathlib.Path
    reported: dict[str, Fingerprint]
    pending: dict[str, Fingerprint]
    pending_since: float


def _load_reported(path: pathlib.Path) -> dict[str, Fingerprint]:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def open_watch(
    state_dir: pathlib.Path, paths: abc.Sequence[pathlib.Path], me: str, quiet: float
) -> FileWatch:
    """A path with no saved fingerprint takes its current state as its baseline."""
    state_dir.mkdir(parents=True, exist_ok=True)
    resolved = [p.resolve() for p in paths]
    reported_path = state_stem(state_dir, resolved, me).with_suffix(".reported.json")
    current = {str(p): _fingerprint(p) for p in resolved}
    saved = _load_reported(reported_path)
    reported = {k: saved.get(k, fp) for k, fp in current.items()}
    if reported != saved:
        reported_path.write_text(json.dumps(reported))
    return FileWatch(resolved, quiet, reported_path, reported, current, time.time())


def poll(w: FileWatch, deliver: ty.Callable[[str], None]) -> bool:
    """Read every path once and deliver at most one event; True if one was delivered.

    State advances only after `deliver` returns, so a delivery that raises leaves the
    change for the next waiter.
    """
    current = {str(p): _fingerprint(p) for p in w.paths}
    if current != w.pending:
        w.pending, w.pending_since = current, time.time()
        if w.quiet:
            return False

    if current == w.reported or time.time() - w.pending_since < w.quiet:
        return False

    deliver(
        "; ".join(
            _describe(p, w.reported[p], new) for p, new in current.items() if new != w.reported[p]
        )
    )
    w.reported = current
    w.reported_path.write_text(json.dumps(current))
    return True
