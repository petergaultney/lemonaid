import os
import tempfile
from pathlib import Path

# Set before lemonaid is imported, since its log handler opens the file at import.
_LAST_RESORT = Path(tempfile.mkdtemp(prefix="lemonaid-tests-"))
os.environ["LEMONAID_LOG"] = str(_LAST_RESORT / "lemonaid.log")

import pytest  # noqa: E402

from lemonaid.inbox import db  # noqa: E402
from lemonaid.lemon_watchers import watcher  # noqa: E402
from lemonaid.messages import service  # noqa: E402

# The per-test fixtures below are monkeypatches, and `monkeypatch.undo()` in a test
# reverts them all, which once pointed a test's migration at the live database and
# the real homes. These process-wide defaults are what an undone test falls back to.
for _name, _path in (
    ("LEMONAID_DB", "lemonaid.db"),
    ("LEMONAID_CONFIG", "config.toml"),
    ("LEMONAID_STATE_DIR", "state"),
    ("LEMONAID_BRIEFS_DIR", "briefs"),
    ("LEMONAID_LEMONS_DIR", "lemons"),
    ("LEMONAID_LEGACY_BRIEFS_DIR", "brief-lemons"),
    ("LEMONAID_CLAUDE_SKILLS_DIR", "claude/skills"),
    ("LEMONAID_CODEX_SKILLS_DIR", "codex/skills"),
):
    os.environ[_name] = str(_LAST_RESORT / _path)
os.environ["TMUX"] = "/nonexistent/lemonaid-tests,0,0"


@pytest.fixture(autouse=True)
def _no_real_tmux(monkeypatch):
    """Point every un-stubbed `tmux` call at a socket that does not exist.

    Setters in tmux/scratch.py mirror state into tmux options, so a test that
    only meant to exercise a file write would otherwise set options on the
    developer's own server. Tests that want a server start their own and
    override this.
    """
    monkeypatch.setenv("TMUX", "/nonexistent/lemonaid-tests,0,0")


@pytest.fixture(autouse=True)
def _own_database(monkeypatch, tmp_path):
    """Every test gets an empty inbox of its own.

    Constructing a LemonaidApp starts its watcher, and a watcher reading the
    real inbox archived four live sessions the moment the tmux it could see was
    a test server with none of their ttys. It also made layout tests depend on
    whatever happened to be in the inbox at the time.
    """
    monkeypatch.setattr(db, "get_db_path", lambda: tmp_path / "lemonaid.db")


@pytest.fixture(autouse=True)
def _own_state_and_config(monkeypatch, tmp_path):
    """Scratch-pane and back-location state, the config, and briefs stay out of $HOME."""
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(tmp_path / "briefs"))
    monkeypatch.delenv("LEMONAID_MESSAGES_DIR", raising=False)
    monkeypatch.setenv("LEMONAID_CONFIG", str(tmp_path / "config.toml"))


@pytest.fixture(autouse=True)
def _own_skill_dirs(monkeypatch, tmp_path):
    """`skills install` links into each harness's skills directory, never the real ones."""
    monkeypatch.setenv("LEMONAID_CLAUDE_SKILLS_DIR", str(tmp_path / "claude" / "skills"))
    monkeypatch.setenv("LEMONAID_CODEX_SKILLS_DIR", str(tmp_path / "codex" / "skills"))


@pytest.fixture(autouse=True)
def _own_watch_state(monkeypatch, tmp_path_factory):
    """Doc waiters' locks, reported threads, and watch lists are shared with live waiters.

    Deleting a live waiter's lock breaks its duplicate detection until it restarts, so
    `$TMPDIR/watch-doc` and the OpenClaw watch lists both move to the test's own
    directories, outside `tmp_path` so tests that list it see only their own files.
    """
    monkeypatch.setenv("TMPDIR", str(tmp_path_factory.mktemp("tmpdir")))
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.setenv("LEMONAID_WATCH_LISTS_DIR", str(tmp_path_factory.mktemp("watch-lists")))


@pytest.fixture(autouse=True)
def _no_detached_delivery_service(monkeypatch):
    """A spawned service outlives the test, and its database is the real one.

    The database override above patches a function, which a child process
    never sees. Tests of starting the service stub `subprocess.Popen` instead.
    """
    monkeypatch.setattr(service, "ensure_running", lambda: None)


@pytest.fixture(autouse=True)
def _watchers_must_not_outlive_tests(_no_real_tmux, _own_database):
    """Fail safely if a test leaves the DB-mutating watcher behind.

    The cleanup runs before the database and TMUX monkeypatches are undone. A
    leaked watcher must never get a chance to observe the developer's real
    inbox while it still carries a test's fake view of tmux.
    """
    yield

    thread = watcher._watcher_thread
    if thread is not None and thread.is_alive():
        watcher.stop_unified_watcher()
        pytest.fail("test leaked the unified watcher thread")
