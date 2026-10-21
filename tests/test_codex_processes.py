import json
import subprocess

import pytest

from lemonaid.codex import processes

_thread_ttys = processes.thread_ttys


def _rollout(tmp_path, name, **meta):
    path = tmp_path / f"rollout-2026-10-20-{name}.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": name, **meta}}) + "\n")
    return path


def test_open_rollouts_distinguish_author_and_reviewer_and_skip_guardian(tmp_path, monkeypatch):
    author = _rollout(tmp_path, "author")
    reviewer = _rollout(tmp_path, "reviewer")
    guardian = _rollout(tmp_path, "guardian", parent_thread_id="author")

    def run(argv, **kwargs):
        output = (
            f"p11\nn{author}\nn{guardian}\np22\nn{reviewer}\n"
            if argv[0] == "lsof"
            else "11 ttys001 /bin/codex --no-daemon\n22 ttys002 /bin/codex --no-daemon\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    assert _thread_ttys() == {"author": {"/dev/ttys001"}, "reviewer": {"/dev/ttys002"}}


@pytest.mark.parametrize(
    "process", ["11 ?? /bin/codex", "11 ttys001 /bin/codex app-server --listen stdio://"]
)
def test_shared_and_detached_processes_cannot_identify_a_terminal(tmp_path, monkeypatch, process):
    path = _rollout(tmp_path, "root")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=f"p11\nn{path}\n" if argv[0] == "lsof" else process, stderr=""
        ),
    )
    assert _thread_ttys() == {}


def test_failed_probe_is_unknown(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied"))
    )
    assert _thread_ttys() is None


_scoped_thread_ttys = processes.thread_ttys_for_tty


def test_notify_owner_probe_is_scoped_to_hook_tty(tmp_path, monkeypatch):
    author = _rollout(tmp_path, "author")
    guardian = _rollout(tmp_path, "guardian", parent_thread_id="author")
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        if argv[0] == "ps":
            assert argv == ["ps", "-t", "ttys001", "-o", "pid=,tty=,args="]
            output = "11 ttys001 /bin/codex --no-daemon\n12 ttys001 /bin/zsh\n"
        else:
            assert argv == ["lsof", "-a", "-c", "codex", "-p", "11", "-Fpn"]
            output = f"p11\nn{author}\nn{guardian}\n"
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    assert _scoped_thread_ttys("/dev/ttys001") == {"author": {"/dev/ttys001"}}
    assert len(seen) == 2


def test_scoped_probe_does_not_treat_app_server_as_terminal_owner(tmp_path, monkeypatch):
    root = _rollout(tmp_path, "root")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout="11 ttys001 /bin/codex app-server --listen stdio://\n"
            if argv[0] == "ps"
            else f"p11\nn{root}\n",
            stderr="",
        ),
    )
    assert _scoped_thread_ttys("/dev/ttys001") == {}
