"""Keep a lemon's PO box card in step with the `PO box: yes` toggle in its brief.

The watcher calls `sync` on each pass. Turning the toggle on registers the lemon, and its
card is renewed while the watcher runs. Turning it off, or the brief reaching `done`,
removes the card and moves unread mail to the local mailbox.
"""

import datetime
from pathlib import Path

from .. import po_box_config
from ..brief import flags, frontmatter, status
from ..log import get_logger
from ..messages import store
from . import cards, inbox

_log = get_logger("po_box.enrollment")

LABEL = "PO box"


def _close(card: cards.Card, local_mailbox: Path) -> None:
    local_mailbox.mkdir(parents=True, exist_ok=True)
    with store.receive_lock(local_mailbox, wait=False) as held:
        if not held:
            return  # a receiver is reading the box; the next pass closes it

        moved = inbox.unread_to_local(card.inbox, local_mailbox)
        cards.remove(card)
    _log.info("closed %s's PO box, moving %d unread message(s) home", card.address, moved)


def sync(
    config: po_box_config.PoBoxConfig, brief: Path, local_mailbox: Path, now: datetime.datetime
) -> cards.Card | None:
    """The lemon's live card after matching it to *brief*, or None when it has no PO box."""
    if config.root is None or not config.owner or not config.root.is_dir():
        return None

    card = cards.registered(config.root, config.owner, local_mailbox.name)
    try:
        text = brief.read_text(encoding="utf-8")
        frontmatter.fields(text)
    except (OSError, UnicodeError, ValueError) as error:
        _log.warning(
            "can't read %s for its PO box toggle; leaving the box as it is: %s", brief, error
        )
        return card

    parts = status.split(text)
    if not flags.is_on(text, LABEL) or parts.status == "done":
        if card is not None:
            _close(card, local_mailbox)
        return None

    title, area = parts.title, parts.area.strip()
    if card is not None and (card.title, card.area) == (title, area):
        return cards.renew_if_due(card, now)

    try:
        written = cards.register(config.root, config.owner, local_mailbox.name, title, area, now)
    except (ValueError, OSError) as error:
        _log.warning("can't open a PO box for %s: %s", local_mailbox.name, error)
        return None

    if card is None:
        _log.info("opened a PO box for %s", written.address)
    return written
