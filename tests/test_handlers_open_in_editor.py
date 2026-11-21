import subprocess

from lemonaid import handlers
from lemonaid.config import Config


def test_a_reply_row_opens_its_file_in_the_editor(monkeypatch) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **_: ran.append(argv) or subprocess.CompletedProcess(argv, 0),
    )

    handled = handlers.handle_notification({"open_in_editor": "/tmp/review.md"}, Config())

    assert handled is True
    assert ran == [[ran[0][0], "-m", "lemonaid", "editor", "open", "/tmp/review.md", "--focus"]]


def test_with_no_editor_the_row_opens_the_file_the_usual_way(monkeypatch) -> None:
    ran: list[list[str]] = []

    def run(argv, **_):
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "editor" in argv else 0)

    monkeypatch.setattr(subprocess, "run", run)

    handled = handlers.handle_notification({"open_in_editor": "/tmp/review.md"}, Config())

    assert handled is True
    assert ran[-1] == ["open", "/tmp/review.md"]
