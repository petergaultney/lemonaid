import subprocess
import sys
import threading

import pytest

from lemonaid import cli
from lemonaid.audit import actor
from lemonaid.brief import sweep_service
from lemonaid.watch import reconcile


@pytest.fixture
def started(monkeypatch) -> list[list[str]]:
    found: list[list[str]] = []
    monkeypatch.setattr(reconcile, "editable_install", lambda: False)
    monkeypatch.setattr(reconcile, "after_install", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kwargs: found.append(argv))
    return found


def test_the_host_starts_one_sweep_a_day_capped_by_the_config(started):
    service = sweep_service.service()
    for _ in range(2):
        service.tick(threading.Event())
    sweep_service.start_due()

    assert [argv[-6:] for argv in started] == [
        ["brief", "archive", "--idle-days", "14", "--max", "20"]
    ]


def test_a_command_starts_no_sweep(monkeypatch, started):
    monkeypatch.setattr(sys, "argv", ["lemonaid", "config", "path"])

    cli.main()

    assert started == []


def test_a_dev_install_starts_no_sweep(monkeypatch, started):
    monkeypatch.setattr(reconcile, "editable_install", lambda: True)

    sweep_service.start_due()

    assert started == []


def test_the_sweep_names_itself_as_the_actor_rather_than_the_lemon_that_started_it(monkeypatch):
    envs: list[dict] = []
    monkeypatch.setattr(reconcile, "editable_install", lambda: False)
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kwargs: envs.append(kwargs["env"]))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")

    sweep_service.start_due()

    assert envs[0][actor.ACTOR_ENV] == "idle sweep"
