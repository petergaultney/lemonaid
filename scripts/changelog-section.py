#!/usr/bin/env python3
"""Print one version's section of CHANGES.md, without its heading: the GitHub Release notes.

    scripts/changelog-section.py 0.58.3 [CHANGES.md]

A section starts at `# <version> (<date>)` (older ones use `##`) and runs to the
next version heading. Exits 1 when the version has no section, so a release
can't go out without a changelog entry.
"""

import re
import sys
from collections import abc
from pathlib import Path

_VERSION_HEADING = re.compile(r"^#{1,2} (\d+\.\d+\.\d+)\b")


def section(lines: abc.Iterable[str], version: str) -> str | None:
    found: list[str] | None = None
    for line in lines:
        heading = _VERSION_HEADING.match(line)
        if heading:
            if found is not None:
                break

            if heading.group(1) == version:
                found = []
                continue

        if found is not None:
            found.append(line)

    return None if found is None else "".join(found).strip() + "\n"


def main() -> int:
    version = sys.argv[1]
    changes = Path(sys.argv[2] if len(sys.argv) > 2 else "CHANGES.md")
    with changes.open() as f:
        notes = section(f, version)
    if notes is None:
        print(f"{changes} has no section for {version}", file=sys.stderr)
        return 1

    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
