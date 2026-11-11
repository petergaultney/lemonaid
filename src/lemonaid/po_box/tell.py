"""`tell owner/lemon`: send a message to the PO box of a lemon on someone else's machine."""

import datetime
import sys

from .. import po_box_config
from ..messages import receipts
from . import cards, inbox


def is_address(target: str) -> bool:
    return "/" in target


def send(target: str, body: str, sender: str, config: po_box_config.PoBoxConfig) -> None:
    """Prints the message ID, or exits 1 with the reason it wasn't sent."""
    if config.root is None or not config.owner:
        print("PO boxes aren't set up: set [po-box] root and owner in config.toml", file=sys.stderr)
        raise SystemExit(1)

    now = datetime.datetime.now(datetime.UTC)
    try:
        card = cards.find(config.root, target, now)
        path = inbox.send(card, body, f"{config.owner}: {sender}")
    except (LookupError, ValueError, OSError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from None

    print(receipts.message_id(path))
    print(
        f"sent to {card.address}'s PO box; its registration runs to {card.expires.isoformat(timespec='minutes')}",
        file=sys.stderr,
    )
