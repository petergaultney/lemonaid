"""Classify a changed file path into a diff-stats category."""

import os
import re
from collections.abc import Callable

# first match wins
_RULES: list[tuple[str, Callable[[str, str], bool]]] = [
    ("lockfiles", lambda p, b: b.endswith((".lock", "lock.json"))),
    ("notebooks", lambda p, b: b.endswith(".ipynb")),
    ("CI", lambda p, b: p.startswith(".github/")),
    ("tests", lambda p, b: "/tests/" in p or b.startswith("test_") or b.startswith("conftest")),
    (
        # Markdown that ships inside a package (lemon tool docs, KB skills,
        # instruction files) is behavior-bearing runtime material, not repo
        # documentation - and definitely not logic. Keep it out of both bins.
        "runtime-docs",
        lambda p, b: b.endswith(".md") and ("/src/" in p or p.startswith("src/")),
    ),
    ("docs", lambda p, b: b.endswith(".md") or "/docs/" in p or p.startswith("docs/")),
    (
        "config",
        lambda p, b: b.endswith((".toml", ".cfg", ".ini", ".json"))
        or b.startswith("Dockerfile")
        or (b.endswith((".yml", ".yaml")) and not p.startswith(".github/")),
    ),
    ("scripts", lambda p, b: "/scripts/" in p or p.startswith("scripts/")),
]

_BRACE_RENAME = re.compile(r"\{.+ => (.+?)\}")


def normalize_rename(filepath: str) -> str:
    """Resolve git's rename syntax to the destination path.

    Handles both 'old => new' and brace forms like 'foo/{old => new}/bar'.
    """
    if " => " not in filepath:
        return filepath

    m = _BRACE_RENAME.search(filepath)
    if m:
        return _BRACE_RENAME.sub(m.group(1), filepath)

    return filepath.split(" => ", 1)[1]


def categorize(filepath: str) -> str:
    base = os.path.basename(filepath)
    for name, test in _RULES:
        if test(filepath, base):
            return name

    return "code"
