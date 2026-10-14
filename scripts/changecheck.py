"""What a pull request may change in changes/, CHANGES.md and the version.

A PR adds exactly one change file, adds no version to pyproject.toml, and leaves
CHANGES.md alone. Change files already on main are never edited or removed: a release is made of
the files added since the previous tag.
"""

from collections import abc

import changefiles

CHANGES_DIR = "changes/"


def _change_paths(
    changed: abc.Iterable[tuple[str, str]],
) -> abc.Iterator[tuple[str, str]]:
    for status, path in changed:
        if path.startswith(CHANGES_DIR) and path != CHANGES_DIR + changefiles.README:
            yield status, path.removeprefix(CHANGES_DIR)


def check(
    base_version: str | None,
    head_version: str | None,
    changed: abc.Iterable[tuple[str, str]],
    read: abc.Callable[[str], str],
) -> abc.Iterator[str]:
    """Problems with a PR, given its `(status, path)` changes from `git diff --name-status
    --no-renames` and a reader of its files by path."""
    changed = list(changed)
    if base_version != head_version:
        yield f"pyproject.toml's version changed ({base_version} -> {head_version}); it comes from the release tag"

    if any(path == "CHANGES.md" for _, path in changed):
        yield "CHANGES.md is the record before changes/ existed; add a change file instead"

    added: list[str] = []
    for status, name in _change_paths(changed):
        if status == "A":
            added.append(name)
        else:
            yield f"changes/{name} ({status}): a PR only adds its own change file"

    if len(added) != 1:
        yield f"a PR adds exactly one change file; this one adds {len(added)}"

    for name in added:
        try:
            changefiles.parse(name, read(CHANGES_DIR + name))
        except changefiles.MalformedChange as err:
            yield str(err)
