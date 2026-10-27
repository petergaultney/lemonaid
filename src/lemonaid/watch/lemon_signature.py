"""Whether a GitHub comment is signed by a given lemon: `🍋 StateJob (Reviewer): ...`."""

from collections import abc

from . import signature

LEMON_MARKER = "\N{LEMON}"


def is_signed(body: str, signatures: abc.Iterable[str]) -> bool:
    """True when `body` starts with the lemon marker, then one of `signatures` and a colon."""
    text = body.lstrip()
    if not text.startswith(LEMON_MARKER):
        return False

    rest = text.removeprefix(LEMON_MARKER).lstrip("\N{VARIATION SELECTOR-16}").lstrip()
    return any(s and rest.startswith(f"{s}:") for s in signature.forms(signatures))
