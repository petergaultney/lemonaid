"""`lemonaid watch file`: change detection, state between waiters, and the CLI."""

import pathlib
import subprocess
import sys
import time

import pytest

from lemonaid.watch import delivery, file_events


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


def _poll(w) -> list[str]:
    sent: list[str] = []
    file_events.poll(w, sent.append)
    return sent


def test_a_file_change_is_reported_once(tmp_path, state_dir):
    f = tmp_path / "notes.md"
    f.write_text("one")
    w = file_events.open_watch(state_dir, [f], "me", quiet=0)
    assert _poll(w) == []

    f.write_text("two")

    assert _poll(w) == [f"{f} changed"]
    assert _poll(w) == []


def test_creation_and_removal(tmp_path, state_dir):
    f = tmp_path / "later.md"
    w = file_events.open_watch(state_dir, [f], "me", quiet=0)
    f.write_text("x")
    assert _poll(w) == [f"{f} was created"]
    f.unlink()
    assert _poll(w) == [f"{f} was removed"]


def test_a_directory_reports_added_removed_and_changed_files_only(tmp_path, state_dir):
    d = tmp_path / "inbox"
    d.mkdir()
    (d / "keep.md").write_text("a")
    (d / "gone.md").write_text("b")
    w = file_events.open_watch(state_dir, [d], "me", quiet=0)

    (d / "gone.md").unlink()
    (d / "keep.md").write_text("longer")
    (d / "new.md").write_text("c")
    (d / ".waiter.lock").write_text("")
    (d / "done").mkdir()

    assert _poll(w) == [f"{d}: added new.md; removed gone.md; changed keep.md"]


def test_a_change_waits_until_it_has_been_quiet(tmp_path, state_dir):
    f = tmp_path / "notes.md"
    f.write_text("one")
    w = file_events.open_watch(state_dir, [f], "me", quiet=3600)
    f.write_text("two")

    assert _poll(w) == []
    w.pending_since -= 3600
    assert _poll(w) == [f"{f} changed"]


def test_a_rearmed_waiter_reports_what_changed_while_none_ran(tmp_path, state_dir):
    f = tmp_path / "notes.md"
    f.write_text("one")
    file_events.open_watch(state_dir, [f], "me", quiet=0)
    f.write_text("two")

    assert _poll(file_events.open_watch(state_dir, [f], "me", quiet=0)) == [f"{f} changed"]
    assert _poll(file_events.open_watch(state_dir, [f], "me", quiet=0)) == []


def test_a_rearm_that_spells_the_path_differently_keeps_the_pending_change(
    tmp_path, state_dir, monkeypatch
):
    f = tmp_path / "notes.md"
    f.write_text("one")
    monkeypatch.chdir(tmp_path)
    file_events.open_watch(state_dir, [pathlib.Path("notes.md")], "me", quiet=0)
    f.write_text("two")

    assert _poll(file_events.open_watch(state_dir, [f], "me", quiet=0)) == [
        f"{f.resolve()} changed"
    ]


def test_a_failed_delivery_leaves_the_change_for_the_next_waiter(tmp_path, state_dir):
    f = tmp_path / "notes.md"
    f.write_text("one")
    w = file_events.open_watch(state_dir, [f], "me", quiet=0)
    f.write_text("two")

    def fail(message: str) -> None:
        raise delivery.Failed("codex queue failed")

    with pytest.raises(delivery.Failed):
        file_events.poll(w, fail)
    assert _poll(file_events.open_watch(state_dir, [f], "me", quiet=0)) == [f"{f} changed"]


def _cli(tmp_path, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "lemonaid",
            "watch",
            "file",
            *args,
            "--interval",
            "0.05",
            "--quiet",
            "0",
            "--state-dir",
            str(tmp_path / "state"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_cli_status_duplicate_and_once(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("one")
    assert _cli(tmp_path, "--status", str(f), "--me", "me").stdout == "no waiter running\n"
    argv = [
        sys.executable,
        "-m",
        "lemonaid",
        "watch",
        "file",
        "--wait",
        str(f),
        "--me",
        "me",
        "--once",
        "--interval",
        "0.05",
        "--quiet",
        "0",
        "--state-dir",
        str(tmp_path / "state"),
    ]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
    try:
        for _ in range(600):
            if _cli(tmp_path, "--status", str(f), "--me", "me").returncode == 0:
                break
            time.sleep(0.05)
        second = _cli(tmp_path, "--wait", str(f), "--me", "me", "--once")
        f.write_text("two")
        out, _ = proc.communicate(timeout=20)
    finally:
        proc.kill()

    assert second.returncode == 3
    assert proc.returncode == 0
    assert out == f"{f} changed\n"
