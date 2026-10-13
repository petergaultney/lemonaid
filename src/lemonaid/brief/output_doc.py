"""A brief's `Output-Doc:` line: the document its lemon's work produces, if one was named."""

from pathlib import Path

from . import header_line


def read(text: str) -> Path | None:
    """The path on *text*'s header `Output-Doc:` line, or None without one."""
    value = header_line.read(text, "Output-Doc")

    return Path(value).expanduser() if value else None


def of_brief(brief: Path) -> Path | None:
    """The output doc recorded in the brief file *brief*."""
    return read(brief.read_text())
