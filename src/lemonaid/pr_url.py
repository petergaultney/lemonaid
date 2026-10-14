"""Reading a GitHub pull request URL."""

import re

HOST = "github.com"
_PR_URL = re.compile(r"https://github\.com/([^/\s#?]+/[^/\s#?]+)/pull/(\d+)(?:[/#?]\S*)?")


def parse(text: str) -> tuple[str, str] | None:
    """(owner/name, number) of a pull request URL, including `/files` or `#issuecomment-...` tails."""
    match = _PR_URL.fullmatch(text)

    return (match[1], match[2]) if match else None
