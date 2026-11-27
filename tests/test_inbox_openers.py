import subprocess

from lemonaid import handlers
from lemonaid.config import Config, InboxConfig
from lemonaid.inbox import openers


def _config(**commands: str) -> Config:
    return Config(inbox=InboxConfig(openers=openers.parse(commands)))


def test_a_row_names_an_opener_and_supplies_only_the_path(monkeypatch):
    ran: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: ran.append(argv) or subprocess.CompletedProcess(argv, 0),
    )
    config = _config(editor="my-editor open {path} --focus")

    assert handlers.handle_notification({"opener": "editor", "path": "/notes/a b.md"}, config)
    assert ran == [["my-editor", "open", "/notes/a b.md", "--focus"]]


def test_a_failed_or_unknown_opener_falls_back_to_the_rows_uri(monkeypatch):
    ran: list[list[str]] = []

    def run(argv, **kw):
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "my-editor" else 0)

    monkeypatch.setattr(subprocess, "run", run)
    config = _config(editor="my-editor {path}")
    row = {"path": "/notes/a.md", "open_uri": "file:///notes/a.md"}

    assert handlers.handle_notification({**row, "opener": "editor"}, config)
    assert handlers.handle_notification({**row, "opener": "rm -rf"}, config)
    assert ran == [
        ["my-editor", "/notes/a.md"],
        ["open", "file:///notes/a.md"],
        ["open", "file:///notes/a.md"],
    ]


def test_an_opener_without_a_path_placeholder_is_ignored(capsys):
    assert openers.parse({"editor": "my-editor", "ok": "x {path}"}) == {"ok": ("x", "{path}")}
    assert "must be a command that uses {path}" in capsys.readouterr().err
