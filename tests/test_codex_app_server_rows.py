"""Codex sessions hosted by the shared app-server daemon, and their dead rows.

The daemon keeps the controlling tty of the TUI that started it, so a hook under
it reported that one pane for every Codex session, and no tty once the pane
closed. A row with no tty was never archived, and selecting it after its session
was killed offered nothing but an error.
"""

import json
import shutil
import subprocess
import time

import pytest

from lemonaid.codex import hosting
from lemonaid.codex import notify as codex_notify
from lemonaid.inbox import db
from lemonaid.lemon_watchers import untracked, watcher

_DAEMON = (
    "/Users/me/.codex/packages/app-server-daemon/releases/0.159.0/bin/codex "
    "app-server --listen unix:// --managed-daemon"
)
_THREAD = "01a0ee30-a636-7e50-9119-c4e7e5cc8af9"
_CWD = "/work/review"


def _process_tree(monkeypatch, chain: list[str]) -> None:
    """`ps` answers for a hook whose ancestors are *chain*, nearest first, then pid 1."""
    pids = {
        100 + i: (100 + i + 1 if i + 1 < len(chain) else 1, args) for i, args in enumerate(chain)
    }
    monkeypatch.setattr(hosting.os, "getpid", lambda: 100)

    def run(argv, **kwargs):
        ppid, args = pids[int(argv[-1])]
        return subprocess.CompletedProcess(argv, 0, stdout=f"{ppid:>5} {args}\n", stderr="")

    monkeypatch.setattr(hosting.subprocess, "run", run)


def test_a_hook_under_the_daemon_is_hosted(monkeypatch):
    _process_tree(
        monkeypatch,
        ["python lemonaid codex notify", "/Apps/SkyComputerUseClient turn-ended", _DAEMON],
    )

    assert hosting.under_app_server()


def test_a_hook_under_a_tui_is_not(monkeypatch):
    _process_tree(
        monkeypatch,
        [
            "python lemonaid codex notify",
            "/Apps/SkyComputerUseClient turn-ended",
            "/opt/bin/codex fix the app-server reconnect",
            "xonsh",
        ],
    )

    assert not hosting.under_app_server()


def test_the_desktop_apps_server_counts_despite_its_config_flags():
    assert untracked.is_app_server(
        ["/Apps/codex", "-c", "features.code_mode_host=true", "app-server", "--listen", "stdio://"]
    )


def test_a_hosted_notification_records_no_tty(monkeypatch):
    monkeypatch.setattr(codex_notify.hosting, "under_app_server", lambda: True)
    monkeypatch.setattr(codex_notify, "get_tty", lambda: "/dev/ttys012")
    monkeypatch.setattr(codex_notify, "detect_terminal_switch_source", lambda: "tmux")
    monkeypatch.setattr(codex_notify, "get_git_branch", lambda cwd: None)

    codex_notify.handle_notification(json.dumps({"thread-id": _THREAD, "cwd": _CWD}))

    with db.connect() as conn:
        (row,) = db.get_active(conn)
    assert "tty" not in row.metadata


def _row(channel: str, cwd: str = _CWD, tty: str | None = None) -> untracked.Row:
    return (channel, "sid", cwd, 100.0, False, tty, "msg", "tmux")


def _archived(monkeypatch, rows, directories) -> list[str]:
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name="claude": True)
    archived: list[str] = []
    watcher._archive_stale_sessions(rows, archived.append, {}, {None: {}}, directories)
    return archived


def test_a_codex_row_with_no_codex_in_its_directory_is_archived(monkeypatch):
    """A Claude author still working in the same worktree does not keep it."""
    assert _archived(monkeypatch, [_row(f"codex:{_THREAD}")], {"/elsewhere"}) == [
        f"codex:{_THREAD}"
    ]


def test_a_codex_row_with_codex_in_its_directory_stays(monkeypatch):
    assert _archived(monkeypatch, [_row(f"codex:{_THREAD}")], {_CWD}) == []


def test_an_lsof_that_did_not_answer_archives_nothing(monkeypatch):
    assert _archived(monkeypatch, [_row(f"codex:{_THREAD}")], None) == []


@pytest.mark.parametrize("channel", ["claude:6ea7a38c", "opencode:abc"])
def test_other_harnesses_rows_with_no_tty_stay(monkeypatch, channel):
    """A Claude hook reports the directory its shell moved to, not its pane's."""
    assert _archived(monkeypatch, [_row(channel)], {"/elsewhere"}) == []


def _lsof(monkeypatch, returncode: int, stdout: str = "", stderr: str = "") -> None:
    monkeypatch.setattr(
        untracked.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, returncode, stdout, stderr),
    )


def test_the_daemon_does_not_keep_rows_in_its_directory_alive(monkeypatch):
    """It and its helpers work in the directory of the TUI that started it, not a session's."""

    def run(argv, **kwargs):
        if argv[0] == "lsof":
            out = "p10\nn/work/daemon-start\np11\nn/work/daemon-start\np20\nn/work/review\n"
        else:
            out = (
                f"   10     1 {_DAEMON}\n"
                "   11    10 /opt/bin/codex-code-mode-host\n"
                "   20  5000 /opt/bin/codex review the PR\n"
            )
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(untracked.subprocess, "run", run)

    assert untracked.codex_directories() == {"/work/review"}


def test_lsof_finding_no_codex_is_an_empty_answer(monkeypatch):
    _lsof(monkeypatch, 1)

    assert untracked.codex_directories() == set()


def test_lsof_failing_is_no_answer(monkeypatch):
    _lsof(monkeypatch, 1, stderr="lsof: WARNING: can't stat() ...")

    assert untracked.codex_directories() is None


def test_a_codex_process_keeps_its_row_until_it_exits(tmp_path):
    """Against the real process table, with a stand-in named codex.

    Asking processes rather than tmux: the hook's TMUX is the daemon's, so a row
    records no server, and asking the wrong one archived live sessions.
    """
    worktree = tmp_path / "review"
    worktree.mkdir()
    if not shutil.which("cc"):
        pytest.skip("needs a C compiler for a process named codex")

    # A copied system binary is killed by code signing, and a symlink keeps its target's name.
    source = tmp_path / "codex.c"
    source.write_text("#include <unistd.h>\nint main(void) { sleep(30); return 0; }\n")
    codex = tmp_path / "codex"
    subprocess.run(["cc", str(source), "-o", str(codex)], check=True)
    row = _row(f"codex:{_THREAD}", cwd=str(worktree))
    process = subprocess.Popen([str(codex)], cwd=worktree)
    try:
        time.sleep(0.2)
        running = untracked.codex_directories()
    finally:
        process.kill()
        process.wait()

    assert not untracked.gone(row, running)
    assert untracked.gone(row, untracked.codex_directories())
