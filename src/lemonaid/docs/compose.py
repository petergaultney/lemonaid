"""Turn an event's offers into what the lemon is given now, and the log lines for them.

Claude cuts hook context over 10,000 characters to a preview, so a Claude delivery
stays under `CLAUDE_LIMIT`. What doesn't fit is given as its reminder line, or as a
line naming the doc, and stays undelivered so its next match tries again. A package
doc that doesn't fit waits for the next tool call. A doc too long ever to fit is named
once, for the lemon to read.

When any offer is a `before` trigger's first match, the call is refused, and
everything given goes in the refusal's reason, since the call never ran.
"""

from collections import abc
from dataclasses import dataclass, field

from ..log import get_logger
from . import offers, sections, start, window

_log = get_logger("docs.compose")

CLAUDE_LIMIT = 9_500  # leaves room under Claude's 10,000 for the wrapper text

_REFUSAL = (
    "lemonaid refused this call once, so that you read the rule below before making it. "
    "Make the call again, changed if the rule says so, and it will run.\n\n"
)


@dataclass(frozen=True)
class Outcome:
    entries: list[dict]  # log lines
    context: str = ""  # added to the lemon's context
    refusal: str = ""  # refuses the tool call, with this as the reason


def limit(harness: str) -> int | None:
    return CLAUDE_LIMIT if harness == "claude" else None


@dataclass
class Given:
    entries: list[dict] = field(default_factory=list)  # log lines
    texts: list[str] = field(default_factory=list)
    refused: bool = False

    def context(self) -> str:
        return "" if self.refused else "\n\n".join(self.texts)

    def refusal(self) -> str:
        return _REFUSAL + "\n\n".join(self.texts) if self.refused else ""


def _pointer(offer: offers.Offer) -> str:
    where = f'section "{offer.section}" of ' if offer.section else ""
    return f"{where}{offer.doc.path} applies to what you are doing; read it now."


def _text(offer: offers.Offer, delivery: str) -> str:
    """The text *delivery* carries; raises OSError when the doc can't be read."""
    if delivery == "reminder":
        return f"Reminder from {offer.doc.path}: {offer.doc.reminder}"

    body = sections.text(offer.doc.path.read_text(), offer.section)
    if not body:
        _log.warning("%s has no section %r", offer.doc.path, offer.section)
        return ""

    return start.block(offer.doc.path, body, offer.section)


def _fitted(
    offer: offers.Offer, delivery: str, text: str, room: int, most: int
) -> tuple[str, str, bool] | None:
    """(delivery, text, whether it counts as given) for *offer* in *room* characters, of
    the *most* any one response holds, or None to wait for a later call."""
    if len(text) <= room:
        return delivery, text, True
    if delivery == "reminder":
        return None
    if len(text) > most:  # it will never fit, so its pointer is all it gets
        pointer = _pointer(offer)
        return ("pointer", pointer, True) if len(pointer) <= room else None
    if "package" in offer.source:
        return None

    fallback = (
        ("reminder", _text(offer, "reminder"))
        if offer.doc.reminder
        else ("pointer", _pointer(offer))
    )
    return (*fallback, False) if len(fallback[1]) <= room else None


def compose(state: dict, base: dict, given: abc.Iterable[offers.Offer], limit: int | None) -> Given:
    """What *given* delivers now, recorded in the window *state*; *limit* caps its length
    (None for no cap)."""
    out = Given()
    for offer in given:
        key, whole = f"{offer.doc.path}#{offer.section}", f"{offer.doc.path}#"
        try:
            mtime = offer.doc.path.stat().st_mtime
            delivery = window.delivery(
                state, key, mtime, bool(offer.doc.reminder), whole, offer.before, offer.shadow
            )
            text = _text(offer, delivery) if delivery else ""
        except OSError as e:
            _log.warning("could not read %s: %s", offer.doc.path, e)
            continue
        if not text:
            continue

        counted = True
        if not offer.shadow:
            # The refusal's prefix is reserved in every response, since a later offer
            # may still turn this one into a refusal.
            most = limit - len(_REFUSAL) if limit is not None else len(text)
            room = most - sum(len(t) + 2 for t in out.texts) if limit is not None else most
            fitted = _fitted(offer, delivery, text, room, most)
            if fitted is None:
                continue

            refusing = delivery == "refuse"
            delivery, text, counted = fitted
            out.texts.append(text)
            out.refused |= refusing and counted
        if counted:
            window.given(state, key, mtime, "package" in offer.source, offer.shadow)
        out.entries.append(
            {
                **base,
                "kind": "doc",
                "doc": str(offer.doc.path),
                "section": offer.section,
                **offer.source,
                "delivery": delivery,
                "chars": len(text),
                "shadow": offer.shadow,
            }
        )
    return out
