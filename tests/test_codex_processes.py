import json
import os
import subprocess

import pytest

from lemonaid.codex import processes

_thread_ttys = processes.thread_ttys
_open_threads = processes.open_threads


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


@pytest.mark.parametrize(
    "process", ["11 ?? /bin/codex", "11 ttys001 /bin/codex app-server --listen stdio://"]
)
def test_a_rollout_open_only_in_the_daemon_is_still_an_open_thread(tmp_path, monkeypatch, process):
    path = _rollout(tmp_path, "01a16433-b2ad-7421-ac7f-60d55c49edfd")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=f"p11\nn{path}\n" if argv[0] == "lsof" else process, stderr=""
        ),
    )
    assert _thread_ttys() == {}
    assert _open_threads() == {"01a16433-b2ad-7421-ac7f-60d55c49edfd"}


def test_a_failed_open_threads_probe_is_unknown(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied"))
    )
    assert _open_threads() is None


_THREAD = "019a0000-0000-7000-8000-000000000001"


def _counted_lsof(monkeypatch, tmp_path, returncode=0):
    path = _rollout(tmp_path, _THREAD)
    asked = []

    def run(argv, **kwargs):
        asked.append(argv[0])
        return subprocess.CompletedProcess(argv, returncode, stdout=f"p11\nn{path}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    return asked


def test_a_recent_listing_from_any_process_is_used_instead_of_lsof(monkeypatch, tmp_path):
    asked = _counted_lsof(monkeypatch, tmp_path)

    assert _open_threads() == {_THREAD}
    assert _open_threads(max_age=15) == {_THREAD}
    assert asked == ["lsof"]


def test_an_old_listing_or_none_wanted_runs_lsof_again(monkeypatch, tmp_path):
    asked = _counted_lsof(monkeypatch, tmp_path)
    _open_threads()
    old = processes._shared().stat().st_mtime - 30
    os.utime(processes._shared(), (old, old))

    _open_threads(max_age=15)
    _open_threads()

    assert asked == ["lsof", "lsof", "lsof"]


def test_a_failed_listing_is_not_kept(monkeypatch, tmp_path):
    _counted_lsof(monkeypatch, tmp_path, returncode=2)

    assert _open_threads() is None
    assert not processes._shared().exists()


def test_executable_is_that_of_a_process_with_the_thread_open(tmp_path, monkeypatch):
    thread = "01a1e7ad-bbe3-73c3-bbf9-dd42257d3b33"
    mine, other = (
        _rollout(tmp_path, thread),
        _rollout(tmp_path, "01a1e7ad-bbb7-7c82-a5f8-d57796a4dab2"),
    )
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\n")
    codex.chmod(0o755)

    def run(argv, **kwargs):
        output = f"p11\nn{other}\np22\nn{mine}\n" if argv[0] == "lsof" else f"{codex}\n"
        assert argv[0] == "lsof" or argv[-1] == "22"
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")

    def no_proc(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(os, "readlink", no_proc)
    assert processes.executable(thread) == str(codex)
    assert processes.executable("01a1e6af-a8f9-7040-aed2-8d46f618db65") == ""
