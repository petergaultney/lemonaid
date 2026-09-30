"""Every client attached to a doomed session is moved out before it is killed."""

import shutil
import subprocess
import time
import uuid

import pytest

from lemonaid.places import escape, teardown


def _tmux_sessions(monkeypatch, listing: str) -> None:
    def _run(argv, **kwargs):
        class _Result:
            stdout = listing
            returncode = 0

        return _Result()

    monkeypatch.setattr(escape.subprocess, "run", _run)


def test_escape_target_prefers_where_you_came_from(monkeypatch):
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: ("earlier", "%1"))

    assert escape._escape_target("doomed") == "earlier"


def test_escape_target_ignores_a_back_location_that_is_the_doomed_session(monkeypatch):
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: ("doomed", "%1"))
    _tmux_sessions(monkeypatch, "100 older\n200 newer\n300 doomed\n")

    assert escape._escape_target("doomed") == "newer"


def test_escape_target_falls_back_to_most_recently_active(monkeypatch):
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 older\n300 newest\n200 middle\n")

    assert escape._escape_target("doomed") == "newest"


def test_escape_target_skips_lemonaid_internal_sessions(monkeypatch):
    """The scratch pane and reapers are not places to be dropped into."""
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 real\n900 _lma_scratch\n800 _lma_reap_x\n")

    assert escape._escape_target("doomed") == "real"


def test_escape_target_empty_when_nowhere_to_go(monkeypatch):
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 doomed\n")

    assert escape._escape_target("doomed") == ""


def test_escape_prefers_a_session_that_wants_attention(monkeypatch):
    """The most recently active session is often the one you just left."""
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "300 just-left\n100 waiting-on-you\n")
    monkeypatch.setattr(escape, "_wants_attention", lambda available: "waiting-on-you")

    assert escape._escape_target("doomed") == "waiting-on-you"


def test_escape_falls_back_to_recency_when_nothing_is_waiting(monkeypatch):
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 older\n300 newest\n")
    monkeypatch.setattr(escape, "_wants_attention", lambda available: "")

    assert escape._escape_target("doomed") == "newest"


def test_attention_only_counts_sessions_that_are_actually_live(monkeypatch):
    """An archived notification may name a session that no longer exists."""
    monkeypatch.setattr(escape.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 live-one\n")

    class _N:
        name = "long-gone"

    monkeypatch.setattr(escape.db, "get_unread", lambda conn: [_N()])

    assert escape._escape_target("doomed") == "live-one"


def test_evacuate_refuses_when_a_client_has_nowhere_to_go(monkeypatch):
    """Killing the session with no destination would detach the client."""
    monkeypatch.setattr(escape, "_attached_clients", lambda session: [("/dev/ttys001", "")])
    monkeypatch.setattr(escape, "_live_sessions_by_recency", lambda session: [])
    monkeypatch.setattr(escape, "_escape_target", lambda session: "")
    switched = []
    monkeypatch.setattr(escape, "_switch_client", lambda *a: switched.append(a))

    error = escape.evacuate("doomed")

    assert "Nowhere to switch /dev/ttys001" in error
    assert not switched


def test_evacuate_reports_a_failed_switch(monkeypatch):
    monkeypatch.setattr(escape, "_attached_clients", lambda session: [("/dev/ttys001", "")])
    monkeypatch.setattr(escape, "_live_sessions_by_recency", lambda session: ["elsewhere"])
    monkeypatch.setattr(escape, "_escape_target", lambda session: "elsewhere")
    monkeypatch.setattr(escape, "_switch_client", lambda client, session: False)

    assert "nothing was torn down" in escape.evacuate("doomed")


def test_evacuate_refuses_when_tmux_cannot_list_the_clients(monkeypatch):
    """Not knowing who is attached is not the same as nobody being attached."""

    def _unknown(session):
        raise escape.ClientsUnknown("timed out")

    monkeypatch.setattr(escape, "_attached_clients", _unknown)

    assert "nothing was torn down" in escape.evacuate("doomed")


def test_a_toss_whose_clients_are_unknown_starts_no_reaper(monkeypatch, tmp_path):
    def _fail(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 2)

    monkeypatch.setattr(escape.subprocess, "run", _fail)
    spawned = []
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: spawned.append(a))

    assert "Could not tell who is attached" in teardown.toss("doomed", [])
    assert not spawned


def test_a_failed_switch_moves_the_clients_already_switched_back(monkeypatch):
    monkeypatch.setattr(
        escape,
        "_attached_clients",
        lambda session: [("/dev/ttys001", "hq"), ("/dev/ttys002", "hq")],
    )
    monkeypatch.setattr(escape, "_live_sessions_by_recency", lambda session: ["hq"])
    monkeypatch.setattr(escape, "_escape_target", lambda session: "hq")
    switched = []

    def _switch(client, session):
        switched.append((client, session))
        return client != "/dev/ttys002"

    monkeypatch.setattr(escape, "_switch_client", _switch)

    error = escape.evacuate("doomed")

    assert "Could not switch /dev/ttys002" in error
    assert "moved back" not in error
    assert switched == [
        ("/dev/ttys001", "hq"),
        ("/dev/ttys002", "hq"),
        ("/dev/ttys001", "doomed"),
    ]


def test_a_client_that_cannot_be_moved_back_is_reported(monkeypatch):
    monkeypatch.setattr(
        escape,
        "_attached_clients",
        lambda session: [("/dev/ttys001", "hq"), ("/dev/ttys002", "hq")],
    )
    monkeypatch.setattr(escape, "_live_sessions_by_recency", lambda session: ["hq"])
    monkeypatch.setattr(escape, "_escape_target", lambda session: "hq")
    monkeypatch.setattr(
        escape,
        "_switch_client",
        lambda client, session: client == "/dev/ttys001" and session == "hq",
    )

    assert "/dev/ttys001 could not be moved back to 'doomed'" in escape.evacuate("doomed")


def test_evacuate_with_no_clients_switches_nothing(monkeypatch):
    """The caller's own pane being in the session is no reason to move anyone."""
    monkeypatch.setattr(escape, "_attached_clients", lambda session: [])
    switched = []
    monkeypatch.setattr(escape, "_switch_client", lambda *a: switched.append(a))

    assert escape.evacuate("doomed") == ""
    assert not switched


def test_evacuate_sends_each_client_back_to_its_own_last_session(monkeypatch):
    monkeypatch.setattr(
        escape,
        "_attached_clients",
        lambda session: [("/dev/ttys001", "hq"), ("/dev/ttys002", "gone"), ("/dev/ttys003", "")],
    )
    monkeypatch.setattr(escape, "_live_sessions_by_recency", lambda session: ["hq", "recent"])
    monkeypatch.setattr(escape, "_escape_target", lambda session: "recent")
    switched = []
    monkeypatch.setattr(
        escape, "_switch_client", lambda client, session: switched.append((client, session)) or True
    )

    assert escape.evacuate("doomed") == ""
    assert switched == [
        ("/dev/ttys001", "hq"),
        ("/dev/ttys002", "recent"),
        ("/dev/ttys003", "recent"),
    ]


@pytest.fixture
def tmux_server(monkeypatch, tmp_path):
    """A throwaway server with sessions `hq`, `lemon`, and `doomed`.

    $TMUX points the caller at a pane in `lemon`, the way a lemon tossing a
    place by key runs from its own session.
    """
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    started = run("-f", "/dev/null", "new-session", "-d", "-s", "hq")
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    run("new-session", "-d", "-s", "lemon")
    run("new-session", "-d", "-s", "doomed")
    lemon_pane = run("display", "-p", "-t", "lemon", "#{pane_id}").stdout.strip()
    socket = run("display", "-p", "#{socket_path}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.setenv("TMUX_PANE", lemon_pane)
    monkeypatch.setattr(teardown, "reap_log_path", lambda: tmp_path / "reap.log")
    clients: list[subprocess.Popen] = []

    def attach(session: str) -> subprocess.Popen:
        client = subprocess.Popen(
            ["tmux", "-L", name, "-C", "attach", "-t", session],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        clients.append(client)
        return client

    def enter(session: str) -> None:
        pane = run("display", "-p", "-t", session, "#{pane_id}").stdout.strip()
        monkeypatch.setenv("TMUX_PANE", pane)

    try:
        yield run, attach, enter
    finally:
        for client in clients:
            client.kill()
        run("kill-server")


def _client_sessions(run) -> list[str]:
    return run("list-clients", "-F", "#{client_session}").stdout.split()


def _wait_for(condition, seconds: float = 5) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)

    return False


def test_tossing_by_key_from_another_session_keeps_the_watching_client_attached(tmux_server):
    """A lemon in `lemon` tosses `doomed` while a client is watching `doomed`."""
    run, attach, _ = tmux_server
    attach("hq")
    assert _wait_for(lambda: _client_sessions(run) == ["hq"])
    run("switch-client", "-t", "=doomed")  # so the client's last session is hq
    assert _wait_for(lambda: _client_sessions(run) == ["doomed"])

    assert teardown.toss("doomed", []) is None

    assert _wait_for(lambda: "doomed" not in run("list-sessions", "-F", "#{session_name}").stdout)
    assert _client_sessions(run) == ["hq"]


def test_tossing_from_inside_an_unwatched_session_leaves_other_clients_alone(tmux_server):
    """A lemon tosses its own session while the only client is looking at `hq`."""
    run, attach, enter = tmux_server
    enter("doomed")
    attach("hq")
    assert _wait_for(lambda: _client_sessions(run) == ["hq"])

    assert teardown.toss("doomed", []) is None

    assert _wait_for(lambda: "doomed" not in run("list-sessions", "-F", "#{session_name}").stdout)
    assert _client_sessions(run) == ["hq"]
