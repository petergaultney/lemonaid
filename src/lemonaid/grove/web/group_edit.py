"""A phone's edits of one group, made by the same changes as `lemonaid group` and the inbox."""

from ...groups import editing, store
from ...inbox import db

ACTIONS = ("rename", "color", "delete")


def info(name: str) -> dict:
    with db.connect() as conn:
        try:
            group = store.find(conn, name)
        except (LookupError, store.GroupError) as error:
            return {"problem": str(error)}

    return {
        "problem": "",
        "name": group.name,
        "color": group.saved_color,
        "members": len(group.members),
    }


def make(action: str, name: str, answer: str) -> str:
    if action not in ACTIONS:
        return f"no edit {action}"

    with db.connect() as conn:
        try:
            group = store.find(conn, name)
            edit = (
                editing.rename(conn, group, answer)
                if action == "rename"
                else editing.recolor(conn, group, answer)
                if action == "color"
                else editing.delete(conn, group)
            )
        except (LookupError, store.GroupError) as error:
            return str(error)

    return edit.description + (
        f"; couldn't update {len(edit.unwritten)} brief(s)" if edit.unwritten else ""
    )
