"""A document and the files its `@path` imports name, expanded the way Claude Code loads CLAUDE.md.

Each file appears once, in depth-first order after the file that first imports it, under a
`Contents of <path>:` line. An import is `@` at the start of a line or after whitespace,
outside fenced code and code spans; `~` expands, a relative path is relative to the
importing file, and `\\ ` is a space. Imports that name no readable file are logged and skipped.
"""

import re
import typing as ty
from pathlib import Path

from ..log import get_logger

_log = get_logger("hooks.context_docs")

MAX_DEPTH = 4  # Claude Code's own limit on import hops
_IMPORT = re.compile(r"(?:^|(?<=\s))@((?:\\ |[^\s`])+)", re.MULTILINE)
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)


def _prose(text: str) -> ty.Iterator[str]:
    """The paragraphs of `text` outside fenced code blocks."""
    fence = ""
    paragraph: list[str] = []
    for line in text.splitlines():
        if fence:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*", line):
                fence = ""
            continue

        if (opened := _FENCE.match(line)) or not line.strip():
            fence = opened.group(1) if opened else ""
            yield "\n".join(paragraph)
            paragraph = []
        else:
            paragraph.append(line)
    yield "\n".join(paragraph)


def _imports(text: str) -> ty.Iterator[str]:
    for paragraph in _prose(text):
        for match in _IMPORT.finditer(_SPAN.sub("", paragraph)):
            yield match.group(1).replace("\\ ", " ")


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        _log.warning("skipped context doc %s: %s", path, e)
        return None


def _walk(path: Path, depth: int, seen: set[Path]) -> ty.Iterator[tuple[Path, str]]:
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        _log.warning("skipped context doc %s: %s", path, e)
        return

    if resolved in seen:
        return

    seen.add(resolved)
    text = _read(path)
    if text is None:
        return

    yield path, text
    if depth >= MAX_DEPTH:
        if next(_imports(text), None) is not None:
            _log.warning("did not follow imports in %s: deeper than %d", path, MAX_DEPTH)
        return

    for target in _imports(text):
        try:
            child = Path(target).expanduser()
        except RuntimeError as e:
            _log.warning("skipped import %s in %s: %s", target, path, e)
            continue

        yield from _walk(child if child.is_absolute() else path.parent / child, depth + 1, seen)


def expand(root: Path) -> str:
    """`root` and its imports as one text; "" when `root` can't be read."""
    return "\n\n".join(
        f"Contents of {path}:\n\n{text.strip()}" for path, text in _walk(root, 0, set())
    )
