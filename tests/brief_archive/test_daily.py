import subprocess
import sys

import pytest

from lemonaid import cli
from lemonaid.brief import archive_cli
from lemonaid.watch import reconcile

from .shared import brief


@pytest.fixture
def started(monkeypatch) -> list[list[str]]:
    found: list[list[str]] = []
    monkeypatch.setattr(reconcile, "editable_install", lambda: False)
    monkeypatch.setattr(reconcile, "after_install", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kwargs: found.append(argv))
    return found


def test_the_first_command_of_a_day_starts_one_sweep(monkeypatch, started):
    monkeypatch.setattr(sys, "argv", ["lemonaid", "config", "path"])
    for _ in range(2):
        cli.main()

    assert [argv[-4:] for argv in started] == [["brief", "archive", "--idle-days", "14"]]


def test_an_archive_preview_starts_no_sweep(monkeypatch, started, capsys):
    old, _ = brief("old")
    monkeypatch.setattr(
        sys, "argv", ["lemonaid", "brief", "archive", "--idle-days", "30", "--dry-run"]
    )

    with pytest.raises(SystemExit) as stop:
        cli.main()

    assert stop.value.code == 0 and started == []
    assert "old.md" in capsys.readouterr().out and old.exists()


def test_a_dev_install_starts_no_sweep(monkeypatch, started):
    monkeypatch.setattr(reconcile, "editable_install", lambda: True)

    archive_cli.daily()

    assert started == []
