"""One PR per inbox session, with user-configured branch lookups off the UI thread."""

import dataclasses
import sqlite3
from collections import abc
from pathlib import Path
from urllib.parse import urlsplit

from ...brief import attached, layout, pr_table
from ...config import PlaceRoot, PlacesConfig
from ...log import get_logger
from ...places import hooks
from .. import db

_log = get_logger("inbox.pr_numbers")
_REFRESH_SECONDS = 180


@dataclasses.dataclass(frozen=True)
class PR:
    number: str
    url: str = ""


def branch_map(lines: abc.Iterable[str]) -> dict[str, PR]:
    entries: dict[str, set[PR]] = {}
    for line in lines:
        fields = line.split()
        if (
            len(fields) not in (2, 3)
            or not fields[1].isascii()
            or not fields[1].isdecimal()
            or not fields[1].lstrip("0")
        ):
            _log.warning("invalid open_prs line: %r", line)
            continue

        url = fields[2] if len(fields) == 3 else ""
        if url:
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme in ("https", "http") and bool(parsed.hostname)
            except ValueError:
                valid = False
            if not valid or any(ord(c) < 32 or ord(c) == 127 for c in url):
                _log.warning("invalid open_prs URL: %r", url)
                continue
        entries.setdefault(fields[0], set()).add(PR(fields[1].lstrip("0"), url))
    result = {}
    for branch, prs in entries.items():
        numbers = {pr.number for pr in prs}
        urls = {pr.url for pr in prs if pr.url}
        if len(numbers) == 1:
            result[branch] = PR(next(iter(numbers)), next(iter(urls)) if len(urls) == 1 else "")
    return result


def brief_number(text: str) -> PR | None:
    bounds = layout.bounds(text.splitlines())
    if bounds is None:
        return None

    now = layout.parse("\n".join(text.splitlines()[slice(*bounds)]))
    tables = [section for section in now.sections if section.heading.lower() == "prs"]
    if not tables:
        return None

    if len(tables) != 1:
        return None

    rows, problems = pr_table.parse(tables[0].body)
    if problems or len(rows) != 1:
        return None

    found = pr_table.target(rows[0].pr)
    return PR(found[1], pr_table.url(rows[0].pr) or "") if found else None


class Cache:
    """Mutated only on the UI thread; workers return maps through `store`."""

    def __init__(self) -> None:
        self._briefs: dict[Path, tuple[int, int, PR | None]] = {}
        self._maps: dict[tuple[Path, str], tuple[float, dict[str, PR]]] = {}
        self._pending: set[tuple[Path, str]] = set()

    def brief(self, path: Path) -> PR | None:
        try:
            stat = path.stat()
            cached = self._briefs.get(path)
            if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
                return cached[2]

            number = brief_number(path.read_text())
        except (OSError, UnicodeError) as error:
            _log.warning("could not read brief %s: %s", path, error)
            self._briefs.pop(path, None)
            return None

        self._briefs[path] = (stat.st_mtime_ns, stat.st_size, number)
        return number

    def due(self, roots: abc.Iterable[PlaceRoot], now: float) -> list[PlaceRoot]:
        due = []
        for root in roots:
            key = (root.path, root.open_prs)
            cached = self._maps.get(key)
            if (
                root.open_prs
                and key not in self._pending
                and (cached is None or now - cached[0] >= _REFRESH_SECONDS)
            ):
                self._pending.add(key)
                due.append(root)
        return due

    def store(self, root: PlaceRoot, numbers: dict[str, PR], now: float) -> None:
        key = (root.path, root.open_prs)
        self._maps[key] = (now, numbers)
        self._pending.discard(key)

    def number(self, root: PlaceRoot, branch: str) -> PR | None:
        cached = self._maps.get((root.path, root.open_prs))
        return cached[1].get(branch) if cached else None


def rows(
    conn: sqlite3.Connection,
    notifications: abc.Sequence[db.Notification],
    places: PlacesConfig,
    cache: Cache,
) -> dict[str, PR]:
    paths = attached.for_rows(conn, notifications)
    numbers = {}
    for n in notifications:
        cwd, branch = n.metadata.get("cwd", ""), n.metadata.get("git_branch", "")
        root = places.root_for(cwd) if cwd and branch else None
        number = cache.number(root, branch) if root else None
        if not number and n.channel in paths:
            number = cache.brief(paths[n.channel])
        if number:
            numbers[n.channel] = number
    return numbers


def refresh(root: PlaceRoot) -> dict[str, PR]:
    try:
        return branch_map(hooks.run_lines(root, root.open_prs))
    except UnicodeError as error:
        _log.warning("could not decode open_prs output in %s: %s", root.path, error)
        return {}
