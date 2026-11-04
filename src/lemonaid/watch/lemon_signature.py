"""Whether a GitHub comment is signed by a given lemon: `🍋 StateJob (Reviewer): ...`."""

from collections import abc

from . import signature

LEMON_MARKER = "\N{LEMON}"


def _rest(body: str) -> str | None:
    """The text after the lemon marker, or None when *body* doesn't start with it."""
    text = body.lstrip()
    if not text.startswith(LEMON_MARKER):
        return None

    return text.removeprefix(LEMON_MARKER).lstrip("\N{VARIATION SELECTOR-16}").lstrip()


def signer(body: str) -> str:
    """The name, without spaces, that signs *body* (`StateJob` for `🍋 StateJob (Reviewer):`
    or `🍋 Reviewer (StateJob):`); "" for an unsigned body."""
    rest = _rest(body)
    head, colon, _ = (rest or "").partition(":")
    parsed = signature.parse(head) if colon else None
    return parsed[0] if parsed else ""


def is_signed(body: str, signatures: abc.Iterable[str]) -> bool:
    """True when `body` starts with the lemon marker, then one of `signatures` and a colon."""
    rest = _rest(body)
    return rest is not None and any(
        s and rest.startswith(f"{s}:") for s in signature.forms(signatures)
    )
