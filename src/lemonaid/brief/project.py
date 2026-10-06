"""Which project a lemon works in, as the brief card leads with it: `ds-monorepo: apps/unified-asset`."""

from collections import abc
from pathlib import Path

from ..config import PlaceRoot


def _root(roots: abc.Iterable[PlaceRoot], directory: Path) -> PlaceRoot | None:
    resolved = directory.expanduser().resolve()
    return max(
        (r for r in roots if resolved == r.path.resolve() or r.path.resolve() in resolved.parents),
        key=lambda r: len(r.path.parts),
        default=None,
    )


def _below(cwd: Path, place: Path) -> str:
    """*cwd* relative to *place*, or "" when it is *place* or outside it."""
    try:
        relative = cwd.resolve().relative_to(place.resolve())
    except ValueError:
        return ""

    return "" if relative == Path(".") else relative.as_posix()


def label(roots: abc.Iterable[PlaceRoot], place: str, cwd: str, area: str = "") -> str:
    """The project's name, then the part of it the work is in, if known.

    The name is the place root's (its `name`, else its directory's), or the
    place's own directory name outside every root. The part is *area*, which a
    brief's `Area:` line gives, else *cwd* below *place*: a lemon usually runs
    from its place's top, so most of the time only the brief knows it.
    """
    directory = Path(place or cwd) if place or cwd else None
    if directory is None:
        return area

    root = _root(roots, directory)
    name = (root.name or root.path.name) if root else directory.name
    part = area or (_below(Path(cwd), Path(place)) if cwd and place else "")
    if not part or part == name:
        return f"Project: {name}" if part else name

    return f"{name}: {part}"
