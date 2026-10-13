"""A review brief's `Reviews:` line: the pull request it reviews, as a URL."""

from .. import pr_url
from . import header_line


def read(text: str) -> tuple[str, int] | None:
    """(`owner/name`, number) of the PR on *text*'s header `Reviews:` line, or None without one."""
    value = header_line.read(text, "Reviews")
    found = pr_url.parse(value) if value else None

    return (found[0], int(found[1])) if found else None
