"""`lemonaid watch doc` run as a process, the way a harness runs it."""

import os
import stat
import subprocess
import sys
import time

import pytest

_ASK = '{{authorId="1" author="Peter">>is this true?<<}}'

_FAKE_CODEX = """#!/bin/sh
if [ "$1" = queue ]; then printf '%s\\n' "$@" > "$FAKE_CODEX_ARGS"; fi
exit "${FAKE_CODEX_EXIT:-0}"
"""


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(f"# Review\n\nA claim.{_ASK}\n")
    return path


def _argv(tmp_path, *args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "lemonaid",
        "watch",
        "doc",
        *args,
        "--interval",
        "0.05",
        "--state-dir",
        str(tmp_path / "state"),
    ]


def _run(tmp_path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _argv(tmp_path, *args), capture_output=True, text=True, timeout=20, check=False
    )


def _start(tmp_path, *args: str) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        _argv(tmp_path, *args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    deadline = time.monotonic() + 30
    while _run(tmp_path, "--status", args[1], "--me", "Claude").returncode != 0:
        assert proc.poll() is None, f"waiter exited {proc.returncode}: {proc.stdout.read()}"
        assert time.monotonic() < deadline, "waiter never took its lock"
        time.sleep(0.05)
    return proc


def test_once_prints_the_first_event_and_exits(tmp_path, doc):
    result = _run(tmp_path, "--wait", str(doc), "--me", "Claude", "--once")

    assert result.returncode == 0
    assert result.stdout.startswith("1 new or changed unanswered thread(s) in ")
    assert "Peter: is this true?" in result.stdout


def test_status_names_a_running_waiter_and_a_second_one_refuses(tmp_path, doc):
    doc.write_text("# Review\n")  # nothing to report, so the waiter keeps running
    assert _run(tmp_path, "--status", str(doc), "--me", "Claude").stdout == "no waiter running\n"
    proc = _start(tmp_path, "--wait", str(doc), "--me", "Claude", "--once")
    try:
        status = _run(tmp_path, "--status", str(doc), "--me", "Claude")
        second = _run(tmp_path, "--wait", str(doc), "--me", "Claude", "--once")
    finally:
        proc.kill()
        proc.wait()

    assert status.returncode == 0
    assert status.stdout.startswith(f"waiter running: pid {proc.pid} since ")
    assert second.returncode == 3
    assert second.stdout.startswith(f"not started: a waiter for {doc} as Claude is already running")


def test_a_waiter_under_another_name_is_independent(tmp_path, doc):
    doc.write_text("# Review\n")
    proc = _start(tmp_path, "--wait", str(doc), "--me", "Claude", "--once")
    try:
        other = _run(tmp_path, "--status", str(doc), "--me", "Codex")
    finally:
        proc.kill()
        proc.wait()

    assert other.stdout == "no waiter running\n"


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text(_FAKE_CODEX)
    codex.chmod(codex.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    (tmp_path / "codex-home").mkdir()
    args_file = tmp_path / "codex-args"
    monkeypatch.setenv("FAKE_CODEX_ARGS", str(args_file))
    return args_file


def test_codex_thread_queues_the_event_and_exits(tmp_path, doc, fake_codex):
    result = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--codex-thread", "t-123")

    assert result.returncode == 0
    queued = fake_codex.read_text().splitlines()
    assert queued[:4] == ["queue", "--thread", "t-123", "--message"]
    assert queued[4].startswith("watch-doc event: 1 new or changed unanswered thread(s)")
    assert queued[-1].endswith(
        "Use $watch-doc to handle every pending thread, then rearm the waiter."
    )


def test_bare_codex_thread_queues_into_codex_thread_id(tmp_path, doc, fake_codex, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "t-own")

    result = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--codex-thread")

    assert result.returncode == 0
    assert fake_codex.read_text().splitlines()[:3] == ["queue", "--thread", "t-own"]


def test_bare_codex_thread_refuses_without_codex_thread_id(tmp_path, doc, fake_codex, monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)

    result = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--codex-thread")

    assert result.returncode == 2
    assert (
        result.stdout
        == "not started: --codex-thread without a THREAD_ID needs CODEX_THREAD_ID set\n"
    )


def test_a_failed_codex_queue_leaves_the_event_for_the_next_waiter(
    tmp_path, doc, fake_codex, monkeypatch
):
    monkeypatch.setenv("FAKE_CODEX_EXIT", "1")
    failed = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--codex-thread", "t-123")
    monkeypatch.setenv("FAKE_CODEX_EXIT", "0")
    retried = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--once")

    assert failed.returncode == 1
    assert "will be reported to the next waiter" in failed.stdout
    assert retried.stdout.startswith("1 new or changed unanswered thread(s)")


def test_codex_mode_refuses_to_start_when_it_could_not_deliver(tmp_path, doc, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    result = _run(tmp_path, "--wait", str(doc), "--me", "Codex", "--codex-thread", "t-123")

    assert result.returncode == 2
    assert result.stdout == "not started: `codex` is not on PATH\n"


@pytest.mark.parametrize(
    "extra",
    [
        ["--wait", "DOC", "--codex-thread", "t", "--openclaw-session", "s"],
        ["--watch-list", "LIST", "--once"],
    ],
)
def test_exclusive_modes_refuse_to_start(tmp_path, doc, extra):
    args = [
        str(doc) if a == "DOC" else str(tmp_path / "l.json") if a == "LIST" else a for a in extra
    ]

    result = _run(tmp_path, *args, "--me", "Claude")

    assert result.returncode == 2
    assert result.stdout.startswith("not started: ")


def _edit_while_waiting(tmp_path, doc, *args: str) -> subprocess.CompletedProcess[str]:
    doc.write_text("# Review\n")
    proc = _start(tmp_path, "--wait", str(doc), "--me", "Claude", "--quiet", "0.2", "--once", *args)
    doc.write_text("# Review\n\nPlease look at the second section.\n")
    try:
        out, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, "")


def test_body_edits_are_reported_by_default(tmp_path, doc):
    result = _edit_while_waiting(tmp_path, doc)

    assert result.returncode == 0
    assert result.stdout.startswith(f"body of {doc} changed (+2/-0 lines), quiet for 0s")


def test_no_edits_reports_comments_only(tmp_path, doc):
    result = _edit_while_waiting(tmp_path, doc, "--no-edits")

    assert result.returncode != 0  # still waiting when killed
    assert result.stdout == ""


def test_editing_then_mine_records_an_edit_for_the_calling_lemon(tmp_path, doc):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")
    }

    def run(flag: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            _argv(tmp_path, flag, str(doc)),
            capture_output=True,
            text=True,
            env={**env, **extra},
            check=False,
        )

    anonymous = run("--editing")
    unannounced = run("--mine", CODEX_THREAD_ID="t1")
    run("--editing", CODEX_THREAD_ID="t1")
    paired = run("--mine", CODEX_THREAD_ID="t1")

    assert anonymous.returncode == 2
    assert anonymous.stdout.startswith("not recorded:")
    assert unannounced.returncode == 2
    assert "--editing" in unannounced.stdout
    assert paired.returncode == 0
    assert list((tmp_path / "state" / "own" / "codex-t1").glob("*.edits"))


def test_a_waiter_on_a_missing_doc_waits_for_it(tmp_path):
    doc = tmp_path / "later.md"
    proc = _start(tmp_path, "--wait", str(doc), "--me", "Claude", "--quiet", "0.2", "--once")
    doc.write_text("# Review\n\nPlease look.\n")
    try:
        out, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()

    assert proc.returncode == 0
    assert out.startswith(f"{doc} was created (+3/-0 lines), quiet for 0s")
