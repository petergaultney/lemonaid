"""Open the scratch pane on the brief of the window a key was pressed in."""

from ..brief import attached, sidebar, target
from ..inbox import db, emoji
from . import here


def show_here() -> bool:
    """Show the invoking window's brief in the scratch pane and focus it.

    False when there is no brief to show, or the sidebar can't hold one (the
    pane is on top, or follow is off); the pane then stays on the inbox.
    """
    if not (invoked := here.window()):
        return False

    session_name, window_index, window_id = invoked
    with db.connect() as conn:
        rows = db.get_active(conn)
        found = target.for_session(
            session_name, rows, attached.for_rows(conn, rows), window_index, emoji.by_channel(conn)
        )

    if not (found.attached or found.dirs):
        return False

    return sidebar.show(found, window_id)
