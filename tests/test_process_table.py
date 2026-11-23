"""Every process from one `ps -A`, with terminals named as `ps -t` names them."""

import shutil
import subprocess
import sys

import pytest

from lemonaid import process_table


def _ps(monkeypatch, out: str, returncode: int = 0) -> list[list[str]]:
    asked: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: (
            asked.append(argv) or subprocess.CompletedProcess(argv, returncode, out, "ps: boom")
        ),
    )
    return asked


@pytest.mark.skipif(sys.platform != "darwin", reason="ps -o tdev is macOS's")
def test_terminals_are_named_as_ps_names_them():
    named = {pid: tty for pid, tty, _ in process_table.listing("pid", "tty", "comm", timeout=5)}
    out = subprocess.run(["ps", "-A", "-o", "pid=,tty="], capture_output=True, text=True)
    ttys = dict(line.split() for line in out.stdout.splitlines() if line.strip())
    both = named.keys() & ttys.keys()

    assert both
    assert {pid: named[pid] for pid in both} == {pid: ttys[pid] for pid in both}


def test_a_column_of_several_words_stays_one_column(monkeypatch):
    monkeypatch.setattr(process_table.sys, "platform", "linux")
    asked = _ps(monkeypatch, "11  pts/3 Mon Nov 16 18:27:18 2026 codex resume abc\n12 ? \n")

    assert process_table.listing("pid", "tty", "lstart", "args", timeout=1) == [
        ["11", "pts/3", "Mon Nov 16 18:27:18 2026", "codex resume abc"]
    ]
    assert asked == [["ps", "-A", "-ww", "-o", "pid=,tty=,lstart=,args="]]


def test_a_failed_ps_raises(monkeypatch):
    _ps(monkeypatch, "", returncode=1)

    with pytest.raises(subprocess.CalledProcessError):
        process_table.listing("tty", "args", timeout=1)


def test_a_sandboxed_process_does_not_try_ps(monkeypatch):
    monkeypatch.setattr(process_table, "sandboxed", lambda: True)
    asked = _ps(monkeypatch, "11 ttys001\n")

    with pytest.raises(PermissionError):
        process_table.listing("pid", "tty", timeout=1)
    assert asked == []


@pytest.mark.skipif(not shutil.which("sandbox-exec"), reason="macOS sandboxes only")
def test_a_process_knows_when_it_runs_in_a_sandbox():
    code = "from lemonaid import process_table; print(process_table.sandboxed())"
    outside = [sys.executable, "-c", code]
    inside = ["sandbox-exec", "-p", "(version 1)(allow default)", *outside]

    assert subprocess.run(outside, capture_output=True, text=True).stdout.split() == ["False"]
    assert subprocess.run(inside, capture_output=True, text=True).stdout.split() == ["True"]
