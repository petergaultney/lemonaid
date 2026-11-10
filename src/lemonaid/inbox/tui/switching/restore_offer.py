"""Selecting the row that says lemons were lost with their terminal: restore them, or dismiss them."""

import subprocess

from textual import events
from textual.widget import Widget

from ....log import LOG_PATH
from ....restore import auto, front_ends
from ..error_screen import ErrorScreen

RESTORE = "restore"
DISMISS = "dismiss"


class RestoreOfferScreen(ErrorScreen):
    """Its accept key restores, `d` dismisses, any other key closes."""

    def on_mount(self) -> None:
        self.query_one(".hint").update(  # type: ignore[attr-defined]
            f"Press {self.accept_key} to restore them, d to dismiss them, any other key to close"
        )

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if self.accepts(event):
            self.dismiss(RESTORE)  # type: ignore[arg-type]
        elif event.character == "d":
            self.dismiss(DISMISS)  # type: ignore[arg-type]
        else:
            self.dismiss("")  # type: ignore[arg-type]


def _run(argv: list[str]) -> None:
    with open(LOG_PATH, "a") as log:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True
        )


def _chosen(widget: Widget, choice: str) -> None:
    if choice == RESTORE and not any(terminal.up() for terminal in front_ends.restorers()):
        widget.notify(
            "Start their terminal first: the inbox restores lemons only into one that runs"
        )
    elif choice == RESTORE:
        _run(["lemonaid", "restore", "--into-running"])
        widget.notify("Restoring the lost lemons; the inbox lists any that don't come back")
    elif choice == DISMISS:
        _run(["lemonaid", "restore", "dismiss", "--all"])
        widget.notify("Dismissed the lost lemons")


def offer(widget: Widget, message: str) -> None:
    widget.app.push_screen(
        RestoreOfferScreen("Lemons lost with their terminal", message, offer="restore them"),
        lambda choice: _chosen(widget, str(choice or "")),
    )


def is_offer(channel: str) -> bool:
    return channel == auto.ASK_CHANNEL
