"""The stdin/stdout loop of an arranger written as a Python function.

`lemonaid inbox arrange serve <file.py>` runs the file's `arrange(snapshot)`
here, in lemonaid's own interpreter, so it can `from lemonaid.inbox.arrange
import answer` and start from `answer.default(snapshot)`. The file is loaded
again whenever its contents change, so an edit takes effect at the next snapshot.
"""

import json
import runpy
import sys
import traceback
from collections import abc
from pathlib import Path
from typing import IO, Any

Arrange = abc.Callable[[dict[str, Any]], Any]


class NoArrange(Exception):
    """The file defines no `arrange` function."""


def load(path: Path) -> Arrange:
    fn = runpy.run_path(str(path)).get("arrange")
    if not callable(fn):
        raise NoArrange(f"{path} defines no function arrange(snapshot)")

    return fn


def reloading(path: Path) -> abc.Callable[[], Arrange]:
    """`arrange` from *path*, loaded again whenever the file's contents change."""
    loaded: dict[bytes, Arrange] = {}

    def current() -> Arrange:
        source = path.read_bytes()
        if source not in loaded:
            loaded.clear()
            loaded[source] = load(path)
        return loaded[source]

    return current


def serve(
    arrange: abc.Callable[[], Arrange],
    stdin: IO[str] = sys.stdin,
    stdout: IO[str] = sys.stdout,
) -> None:
    """Answer each snapshot line on *stdin* with the answer of `arrange()`, until *stdin* closes.

    An error loading the function is answered like an error in it, so `lma`
    shows it and the next snapshot tries again.
    """
    for line in stdin:
        try:
            out = json.dumps(arrange()(json.loads(line)))
        except Exception as e:  # the user's code: report it to lma and keep serving
            traceback.print_exc(file=sys.stderr)
            out = json.dumps({"error": f"{type(e).__name__}: {e}"})
        stdout.write(out + "\n")
        stdout.flush()
