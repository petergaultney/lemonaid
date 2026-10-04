"""`lemonaid watch openclaw` and the OpenClaw delivery adapter."""

import argparse
import hashlib
import json
import stat
import subprocess
import sys

import pytest

from lemonaid.watch import delivery, openclaw_cli, watch_list

_FAKE_OPENCLAW = """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_OPENCLAW_ARGS"
echo "banner line"
echo "${FAKE_OPENCLAW_RESULT:-{\\"ok\\": true}}"
exit "${FAKE_OPENCLAW_EXIT:-0}"
"""


@pytest.fixture
def lists_dir(tmp_path):
    return tmp_path / "lists"


@pytest.fixture
def started(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda argv, check: calls.append(argv))
    return calls


def test_list_names_keep_their_format(lists_dir):
    """A waiter started after a rename would not find the lists already there."""
    key = "agent:main:doc-filing-worker-v2:abc"

    assert openclaw_cli.list_path(lists_dir, key) == (
        lists_dir / f"openclaw-{hashlib.sha1(key.encode()).hexdigest()[:12]}.json"
    )


def test_start_adds_the_doc_and_starts_a_lemonaid_waiter(tmp_path, lists_dir, started):
    doc = tmp_path / "note.md"

    openclaw_cli.start(lists_dir, doc, "agent:main:x", "Meyer", "agent:main:main", 7)

    target = openclaw_cli.list_path(lists_dir, "agent:main:x")
    assert list(watch_list.read(target)) == [str(doc.resolve())]
    assert json.loads(target.with_suffix(".session").read_text()) == {"session_key": "agent:main:x"}
    [argv] = started
    assert argv[:3] == ["systemd-run", "--user", "--collect"]
    assert argv[3].startswith(f"--unit=watch-doc-{target.stem}-")
    run_at = argv.index(sys.executable)
    assert argv[run_at:] == [
        sys.executable,
        "-m",
        "lemonaid",
        "watch",
        "doc",
        "--watch-list",
        str(target),
        "--me",
        "Meyer",
        "--openclaw-session",
        "agent:main:x",
        "--hq-session",
        "agent:main:main",
        "--idle-expire",
        "604800",
    ]


def test_start_takes_the_doc_from_other_sessions_and_reuses_a_running_waiter(
    tmp_path, lists_dir, started
):
    doc = tmp_path / "note.md"
    openclaw_cli.start(lists_dir, doc, "agent:main:old", "Meyer", "agent:main:main", 7)
    held = watch_list.hold_waiter(openclaw_cli.list_path(lists_dir, "agent:main:new"))

    openclaw_cli.start(lists_dir, doc, "agent:main:new", "Meyer", "agent:main:main", 7)

    assert watch_list.read(openclaw_cli.list_path(lists_dir, "agent:main:old")) == {}
    assert len(started) == 1  # only the first session had no waiter
    assert held is not None
    held.close()


def test_stop_and_list(tmp_path, lists_dir, started, capsys):
    doc = tmp_path / "note.md"
    openclaw_cli.start(lists_dir, doc, "agent:main:x", "Meyer", "agent:main:main", 7)

    openclaw_cli.show(lists_dir)
    openclaw_cli.stop(lists_dir, doc)

    listed, stopped = capsys.readouterr().out.splitlines()
    assert listed == f"agent:main:x\t0.0d idle\t{doc.resolve()}"
    assert stopped == f"stopped watching {doc} for agent:main:x"


@pytest.fixture
def fake_openclaw(tmp_path, monkeypatch):
    cli = tmp_path / "openclaw"
    cli.write_text(_FAKE_OPENCLAW)
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    args_file = tmp_path / "openclaw-args"
    monkeypatch.setenv("FAKE_OPENCLAW_ARGS", str(args_file))
    return cli, args_file


def test_openclaw_delivery_runs_one_idempotent_turn(fake_openclaw):
    cli, args_file = fake_openclaw

    delivery.to_openclaw("agent:main:x", "Meyer", "agent:main:main", str(cli), 1000)("an event")

    argv = args_file.read_text().splitlines()
    assert argv[:5] == ["gateway", "call", "agent", "--json", "--expect-final"]
    params = json.loads(argv[argv.index("--params") + 1])
    assert params["sessionKey"] == "agent:main:x"
    assert params["idempotencyKey"] == hashlib.sha1(b"agent:main:x\0an event").hexdigest()
    assert params["message"].startswith("watch-doc event: an event\n")
    assert 'author="Meyer" authorId="agent:main:x"' in params["message"]


@pytest.mark.parametrize(
    ("result", "code"),
    [
        ('{"ok": false}', "0"),
        ('{"status": "error"}', "0"),
        ("not json", "0"),
        ('{"ok": true}', "1"),
    ],
)
def test_openclaw_delivery_fails_on_an_unsuccessful_turn(fake_openclaw, monkeypatch, result, code):
    cli, _ = fake_openclaw
    monkeypatch.setenv("FAKE_OPENCLAW_RESULT", result)
    monkeypatch.setenv("FAKE_OPENCLAW_EXIT", code)

    with pytest.raises(delivery.Failed):
        delivery.to_openclaw("agent:main:x", "Meyer", "agent:main:main", str(cli), 1000)("e")


def test_openclaw_setup_needs_the_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    assert delivery.openclaw_setup_problem("openclaw") == "`openclaw` is not on PATH"


def _start_args(*argv: str):
    ap = argparse.ArgumentParser()
    openclaw_cli.add_parser(ap.add_subparsers())
    return ap.parse_args(["openclaw", "start", "doc.md", "--session-key", "agent:main:x", *argv])


@pytest.mark.parametrize("me", [(), ("--me", ""), ("--me", "  ")])
def test_start_requires_a_nonblank_me(me):
    with pytest.raises(SystemExit):
        _start_args(*me)


def test_start_passes_me_through():
    assert _start_args("--me", "Sam").me == "Sam"
