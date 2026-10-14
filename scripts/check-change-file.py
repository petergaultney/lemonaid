#!/usr/bin/env python3
"""Check a PR's change file against its base: CI's `changes` workflow runs this.

    scripts/check-change-file.py <base-ref>

Prints each problem and exits 1 if there are any. A PR that needs no change file (docs or
tests only) skips the check with the `no-change-file` label.
"""

import subprocess
import sys
from pathlib import Path

import changecheck
import changefiles

_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_ROOT, check=True, capture_output=True, text=True
    ).stdout


def main() -> int:
    base = sys.argv[1]
    if not _git("ls-tree", "--name-only", base, changecheck.CHANGES_DIR):
        print(f"{base} has no changes/ yet; this PR introduces it")
        return 0

    changed = [
        (line.split("\t")[0], line.split("\t")[-1])
        for line in _git("diff", "--no-renames", "--name-status", f"{base}...HEAD").splitlines()
    ]
    problems = list(
        changecheck.check(
            changefiles.pyproject_version(_git("show", f"{base}:pyproject.toml")),
            changefiles.pyproject_version((_ROOT / "pyproject.toml").read_text()),
            changed,
            lambda path: (_ROOT / path).read_text(),
        )
    )
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(
            "See changes/README.md. A docs- or tests-only PR takes the `no-change-file` label.",
            file=sys.stderr,
        )
        return 1

    print("change file looks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
