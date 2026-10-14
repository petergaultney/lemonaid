"""Change files in changes/: one per PR, versioned only when a release picks them up.

A change file is `YYYY-MM-DD-<two-to-six-word-title>.md`, dated the day the work started.
Its first line names the bump (`# Patch`, `# Minor`, `# Major`) and the rest is the
changelog entry. A release is made of the files added since the previous `v*` tag. See
changes/README.md.
"""

import enum
import re
from collections import abc

README = "README.md"
_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+){1,5}\.md$")
_BUMP_HEADING = re.compile(r"^# (Patch|Minor|Major)\s*$")
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_PYPROJECT_VERSION = re.compile(r'^version = "([^"]*)"$', re.MULTILINE)


class Bump(enum.IntEnum):
    PATCH = 1
    MINOR = 2
    MAJOR = 3


class MalformedChange(ValueError):
    pass


class NothingToRelease(Exception):
    pass


def is_change_file_name(name: str) -> bool:
    return bool(_NAME.match(name))


def parse(name: str, text: str) -> tuple[Bump, str]:
    """The bump and the entry (everything after the bump heading)."""
    if not is_change_file_name(name):
        raise MalformedChange(f"{name}: not named `YYYY-MM-DD-two-to-six-word-title.md`")

    first, _, rest = text.partition("\n")
    heading = _BUMP_HEADING.match(first)
    if not heading:
        raise MalformedChange(f"{name}: first line must be `# Patch`, `# Minor` or `# Major`")

    if not rest.strip():
        raise MalformedChange(f"{name}: has no entry after its bump heading")

    return Bump[heading.group(1).upper()], rest.strip() + "\n"


def _parse_all(changes: abc.Mapping[str, str]) -> list[tuple[Bump, str]]:
    """Every change file in name (so date) order; MalformedChange names each bad one."""
    parsed: list[tuple[Bump, str]] = []
    errors: list[str] = []
    for name in sorted(changes):
        try:
            parsed.append(parse(name, changes[name]))
        except MalformedChange as err:
            errors.append(str(err))

    if errors:
        raise MalformedChange("\n".join(errors))

    if not parsed:
        raise NothingToRelease("no change files since the last release")

    return parsed


def is_version(version: str) -> bool:
    return bool(_VERSION.match(version))


def parse_version(version: str) -> tuple[int, int, int]:
    match = _VERSION.match(version)
    if not match:
        raise ValueError(f"not a release version: {version!r}")

    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def latest_version(versions: abc.Iterable[str]) -> str:
    """The highest of `versions` (tags like `v1.2.3` or bare versions); others are skipped."""
    parsed = [parse_version(v) for v in versions if is_version(v)]
    if not parsed:
        raise ValueError("no release versions to start from")

    return ".".join(map(str, max(parsed)))


def bumped(version: str, bump: Bump) -> str:
    major, minor, patch = parse_version(version)
    if bump is Bump.MAJOR:
        return f"{major + 1}.0.0"

    if bump is Bump.MINOR:
        return f"{major}.{minor + 1}.0"

    return f"{major}.{minor}.{patch + 1}"


def next_version(changes: abc.Mapping[str, str], previous: str) -> str:
    """`previous` raised by the highest bump among `changes` (name -> text), the files
    added since it. Raises MalformedChange or NothingToRelease."""
    return bumped(previous, max(bump for bump, _ in _parse_all(changes)))


def release_notes(changes: abc.Mapping[str, str]) -> str:
    """The entries of `changes` in date order. Raises MalformedChange or NothingToRelease."""
    return "\n".join(entry for _, entry in _parse_all(changes))


def pyproject_version(pyproject: str) -> str | None:
    match = _PYPROJECT_VERSION.search(pyproject)
    return match.group(1) if match else None
