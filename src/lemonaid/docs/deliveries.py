"""`doc-deliveries.jsonl`: a line for each context window a session begins, and one for
each doc or section it is given, or in shadow mode would be.

Every line has `at`, `harness`, `session`, `window`, `mode`, `event` and `shadow`. A
`window` line adds the `source` of its `SessionStart`, the `cwd` and the `packages` the
lemon gets. A `doc` line adds `doc`, `section`, the `package` or `trigger` that brought
it, `delivery` (`full`, `reminder`, or `refuse` for a `before` trigger's first match)
and `chars`, the length of the text delivered.
"""

import json
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import paths

_log = get_logger("docs.deliveries")


def append(entries: abc.Iterable[dict], path: Path | None = None) -> None:
    lines = "".join(json.dumps(entry) + "\n" for entry in entries)
    if not lines:
        return

    path = path or paths.deliveries()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as log:
        log.write(lines)


def read(path: Path | None = None) -> abc.Iterator[dict]:
    path = path or paths.deliveries()
    try:
        with path.open() as log:
            for number, line in enumerate(log, 1):
                try:
                    entry = json.loads(line)
                except ValueError:
                    _log.warning("skipped line %d of %s: not JSON", number, path)
                    continue
                if isinstance(entry, dict):
                    yield entry
    except FileNotFoundError:
        return
