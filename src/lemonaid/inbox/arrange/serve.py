"""The stdin/stdout loop of an arranger written as a Python function.

`lemonaid inbox arrange serve <file.py>` runs the file's `arrange(snapshot)`
here, in lemonaid's own interpreter, so it can `from lemonaid.inbox.arrange
import answer` and start from `answer.default(snapshot)`.
"""

import json
import runpy
import sys
import traceback
from collections import abc
from pathlib import Path
from typing import IO, Any

Arrange = abc.Callable[[dict[str, Any]], Any]


def load(path: Path) -> Arrange:
    fn = runpy.run_path(str(path)).get("arrange")
    if not callable(fn):
        raise SystemExit(f"{path} defines no function arrange(snapshot)")

    return fn


def serve(fn: Arrange, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
    """Answer each snapshot line on *stdin* with `fn`'s answer, until *stdin* closes."""
    for line in stdin:
        try:
            out = json.dumps(fn(json.loads(line)))
        except Exception as e:  # the user's code: report it to lma and keep serving
            traceback.print_exc(file=sys.stderr)
            out = json.dumps({"error": f"{type(e).__name__}: {e}"})
        stdout.write(out + "\n")
        stdout.flush()
