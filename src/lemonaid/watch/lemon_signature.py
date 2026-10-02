"""Whether a GitHub comment is signed by a given lemon: `🍋 Reviewer (StateJob): ...`."""

from collections import abc

LEMON_MARKER = "\N{LEMON}"


def is_signed(body: str, signatures: abc.Iterable[str]) -> bool:
    """True when `body` starts with the lemon marker, then one of `signatures` and a colon."""
    text = body.lstrip()
    if not text.startswith(LEMON_MARKER):
        return False

    rest = text.removeprefix(LEMON_MARKER).lstrip("\N{VARIATION SELECTOR-16}").lstrip()
    return any(s and rest.startswith(f"{s}:") for s in signatures)
