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
