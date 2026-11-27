from pathlib import Path

from lemonaid.inbox import db


def item_channel(doc: Path, lemon: str = "") -> str:
    return f"item:{lemon}|{doc}"


def add_item(doc: Path, lemon: str = "", name: str = "", hide_when_read: bool = True) -> str:
    """What a tool that keeps a row for *lemon* writes, as `inbox add --metadata` would."""
    with db.connect() as conn:
        db.add(
            conn,
            item_channel(doc, lemon),
            "a reply",
            name or f"↳ {doc.name}",
            {"under": lemon, "hide_when_read": hide_when_read, "open_uri": doc.as_uri()},
        )
    return item_channel(doc, lemon)


def read_item(doc: Path, lemon: str = "") -> None:
    with db.connect() as conn:
        found = db.get_by_channel(conn, item_channel(doc, lemon), unread_only=False)
        assert found is not None
        db.mark_read(conn, found.id)
