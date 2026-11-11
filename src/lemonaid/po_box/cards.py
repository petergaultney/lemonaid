"""A lemon's PO box registration: a card at `<root>/lemons/<owner>/<Lemon-ID>/lemon.md`.

Only the owner's lemonaid writes or removes a card. A card past `expires` counts as gone,
so a lemon on a machine that stopped running drops out without anyone deleting it.
"""

import dataclasses
import datetime
import shutil
from collections import abc
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..brief import frontmatter, identity
from ..home import journal

CARD = "lemon.md"
INBOX = "inbox"
LIFETIME = datetime.timedelta(days=2)
RENEW_WITHIN = datetime.timedelta(days=1)


@dataclass(frozen=True)
class Card:
    folder: Path
    owner: str
    lemon_id: str
    title: str
    area: str
    registered: datetime.datetime
    expires: datetime.datetime

    @property
    def address(self) -> str:
        return f"{self.owner}/{self.lemon_id}"

    @property
    def inbox(self) -> Path:
        return self.folder / INBOX

    def expired(self, now: datetime.datetime) -> bool:
        return now >= self.expires


def lemons_dir(root: Path) -> Path:
    return root / "lemons"


def folder(root: Path, owner: str, lemon_id: str) -> Path:
    for name in (owner, lemon_id):
        if not identity.valid(name):
            raise ValueError(f"Not safe as a PO box folder name: {name!r}")

    return lemons_dir(root) / owner / lemon_id


def _text(card: Card) -> str:
    fields = {
        "lemon-id": card.lemon_id,
        "owner": card.owner,
        "area": card.area,
        "registered": card.registered.isoformat(timespec="seconds"),
        "expires": card.expires.isoformat(timespec="seconds"),
    }
    return f"---\n{yaml.safe_dump(fields, sort_keys=False)}---\n# {card.title}\n"


def _save(card: Card) -> Card:
    card.inbox.mkdir(parents=True, exist_ok=True)
    journal.write_atomic(card.folder / CARD, _text(card))
    return card


def title_of(body: str) -> str:
    return next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), "")


def _linked(card_folder: Path) -> bool:
    """Whether any folder between the PO box root and the inbox is a link, which could lead outside it."""
    return any(
        p.is_symlink()
        for p in (card_folder.parent.parent, card_folder.parent, card_folder, card_folder / INBOX)
    )


def read(card_folder: Path) -> Card | None:
    """The card in *card_folder*, or None when there is none, lemonaid can't read it, or it is linked."""
    if _linked(card_folder):
        return None

    try:
        text = (card_folder / CARD).read_text(encoding="utf-8")
        fields = frontmatter.fields(text)
        return Card(
            folder=card_folder,
            owner=card_folder.parent.name,
            lemon_id=card_folder.name,
            title=title_of(frontmatter.split(text)[1]),
            area=str(fields.get("area") or ""),
            registered=datetime.datetime.fromisoformat(str(fields["registered"])),
            expires=datetime.datetime.fromisoformat(str(fields["expires"])),
        )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None


def register(
    root: Path,
    owner: str,
    lemon_id: str,
    title: str,
    area: str,
    now: datetime.datetime,
) -> Card:
    """Write or renew the card, keeping the first registration time.

    Raises ValueError when a folder on the way to the card is a link, which could lead outside
    the shared folder.
    """
    where = folder(root, owner, lemon_id)
    if _linked(where):
        raise ValueError(f"Not writing a PO box card through a link: {where}")

    old = read(where)
    return _save(
        Card(
            where,
            owner,
            lemon_id,
            title,
            area,
            old.registered if old else now,
            now + LIFETIME,
        )
    )


def renew_if_due(card: Card, now: datetime.datetime) -> Card:
    if card.expires - now > RENEW_WITHIN:
        return card

    return _save(dataclasses.replace(card, expires=now + LIFETIME))


def everyone(root: Path) -> abc.Iterator[Card]:
    for card_file in sorted(lemons_dir(root).glob(f"*/*/{CARD}")):
        if (card := read(card_file.parent)) is not None:
            yield card


def find(root: Path, address: str, now: datetime.datetime) -> Card:
    """The live card for `owner/<Lemon-ID or its name half>`; LookupError names why not."""
    owner, _, name = address.partition("/")
    if not owner or not name:
        raise LookupError(f"A PO box address is owner/lemon: {address!r}")

    exact = read(folder(root, owner, name)) if identity.valid(name) else None
    matches = (
        [exact]
        if exact
        else [
            card
            for card in everyone(root)
            if card.owner == owner and identity.brief_name(card.lemon_id) == name
        ]
    )
    if not matches:
        raise LookupError(f"No lemon has a PO box at {address}")

    if len(matches) > 1:
        raise LookupError(f"{address} matches {', '.join(c.lemon_id for c in matches)}")

    card = matches[0]
    if card.expired(now):
        raise LookupError(f"{card.address} registration expired {card.expires.isoformat()}")

    return card


def remove(card: Card) -> None:
    shutil.rmtree(card.folder)


def registered(root: Path | None, owner: str, lemon_id: str) -> Card | None:
    """This machine's card for *lemon_id*, or None when PO boxes aren't set up or it isn't registered."""
    if root is None or not owner:
        return None

    try:
        return read(folder(root, owner, lemon_id))
    except ValueError:
        return None
