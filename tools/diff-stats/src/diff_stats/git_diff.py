"""Extract changed Python sources and line numbers from Git."""

import re
import shlex
import subprocess
import typing as ty
from collections import abc


class PythonFileChanges(ty.NamedTuple):
    old_path: str
    new_path: str
    removed_lines: set[int]
    added_lines: set[int]


class ChangedPythonSource(ty.NamedTuple):
    before: bytes
    after: bytes
    removed_lines: set[int]
    added_lines: set[int]


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _without_git_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path


def _parse_patch(patch: str) -> dict[str, PythonFileChanges]:
    """Track changed line numbers without interpreting hunk contents."""
    changes: dict[str, PythonFileChanges] = {}
    current: PythonFileChanges | None = None
    in_hunk = False
    old_line = 0
    new_line = 0

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            parts = shlex.split(line)
            if len(parts) != 4:
                current = None
                continue

            current = PythonFileChanges(
                old_path=_without_git_prefix(parts[2]),
                new_path=_without_git_prefix(parts[3]),
                removed_lines=set(),
                added_lines=set(),
            )
            changes[current.new_path] = current
            continue

        match = _HUNK_RE.match(line)
        if match and current:
            in_hunk = True
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue

        # Diff metadata precedes the first hunk and is not changed source.
        if not current or not in_hunk:
            continue

        if line.startswith("+"):
            current.added_lines.add(new_line)
            new_line += 1
        elif line.startswith("-"):
            current.removed_lines.add(old_line)
            old_line += 1
        elif line.startswith(" "):
            old_line += 1
            new_line += 1

    return changes


def _git_blob(ref: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def changed_python_sources(
    base: str,
    paths: abc.Iterable[str],
) -> tuple[dict[str, ChangedPythonSource], list[str]]:
    paths = tuple(paths)
    if not paths:
        return {}, []

    patch_result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            f"{base}...HEAD",
            "--",
            "*.py",
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if patch_result.returncode != 0:
        return {}, [f"could not inspect Python diff: {patch_result.stderr.strip()}"]

    merge_base_result = subprocess.run(
        ["git", "merge-base", base, "HEAD"], capture_output=True, text=True
    )
    if merge_base_result.returncode != 0:
        return {}, [f"could not resolve merge base: {merge_base_result.stderr.strip()}"]

    merge_base = merge_base_result.stdout.strip()
    patch_changes = _parse_patch(patch_result.stdout)
    sources: dict[str, ChangedPythonSource] = {}
    warnings: list[str] = []

    for path in paths:
        change = patch_changes.get(path)
        if not change:
            warnings.append(f"could not find Python patch for {path!r}")
            continue

        before = _git_blob(merge_base, change.old_path) if change.removed_lines else b""
        after = _git_blob("HEAD", change.new_path) if change.added_lines else b""
        if before is None or after is None:
            warnings.append(f"could not read Python source for {path!r}")
            continue

        sources[path] = ChangedPythonSource(
            before=before,
            after=after,
            removed_lines=change.removed_lines,
            added_lines=change.added_lines,
        )

    return sources, warnings
