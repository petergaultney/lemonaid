"""The docs under `[docs] roots` whose frontmatter declares something (see
`frontmatter`), in root order.

The index is cached in `paths.index()` by each file's modification time, so a rebuild
reads only the docs that changed. Folders whose names start with `.` are skipped.
"""

import json
import os
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import frontmatter

_log = get_logger("docs.index")


def _markdown(roots: abc.Iterable[Path]) -> abc.Iterator[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue

        for directory, folders, files in os.walk(root):
            folders[:] = sorted(f for f in folders if not f.startswith("."))
            for name in sorted(files):
                if name.endswith(".md"):
                    yield Path(directory) / name


def _dumped(doc: frontmatter.Doc) -> dict:
    return {
        "packages": list(doc.packages),
        "triggers": [t.__dict__ for t in doc.triggers],
        "reminder": doc.reminder,
        "lemons": list(doc.lemons),
    }


def _loaded(path: str, raw: dict) -> frontmatter.Doc:
    return frontmatter.Doc(
        path=Path(path),
        packages=tuple(raw["packages"]),
        triggers=tuple(frontmatter.Trigger(**t) for t in raw["triggers"]),
        reminder=raw["reminder"],
        lemons=tuple(raw["lemons"]),
    )


def _cached(cache: Path) -> dict[str, ty.Any]:
    try:
        loaded = json.loads(cache.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        _log.warning("rebuilding the docs index: could not read %s: %s", cache, e)
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _docs(entries: abc.Mapping[str, ty.Any]) -> list[frontmatter.Doc]:
    return [_loaded(path, entry["doc"]) for path, entry in entries.items() if entry["doc"]]


def build(roots: abc.Iterable[Path], cache: Path) -> list[frontmatter.Doc]:
    """The docs under *roots*, in root order, parsing only those changed since *cache*."""
    cached, entries = _cached(cache), {}
    for path in _markdown(roots):
        try:
            mtime = path.stat().st_mtime
        except OSError as e:
            _log.warning("skipped %s: %s", path, e)
            continue

        hit = cached.get(str(path))
        if isinstance(hit, dict) and hit.get("mtime") == mtime and "doc" in hit:
            entries[str(path)] = hit
        else:
            doc = frontmatter.parse(path, frontmatter.fields(path))
            entries[str(path)] = {"mtime": mtime, "doc": _dumped(doc) if doc else None}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        written = cache.with_name(f"{cache.name}.{os.getpid()}")  # sessions start together
        written.write_text(json.dumps(entries))
        written.replace(cache)
    except OSError as e:
        _log.warning("could not save the docs index to %s: %s", cache, e)
    return _docs(entries)


def read(cache: Path) -> list[frontmatter.Doc]:
    """The docs the last `build` found, without looking at the roots."""
    try:
        return _docs(_cached(cache))
    except (KeyError, TypeError) as e:
        _log.warning("could not read the docs index %s: %s", cache, e)
        return []


def recent(roots: abc.Iterable[Path], cache: Path, max_age: float) -> list[frontmatter.Doc]:
    """The docs under *roots*, rebuilt when *cache* is older than *max_age* seconds, so a
    doc added or changed reaches running lemons without each walking the roots."""
    try:
        fresh = time.time() - cache.stat().st_mtime < max_age
    except OSError:
        fresh = False
    return read(cache) if fresh else build(roots, cache)
