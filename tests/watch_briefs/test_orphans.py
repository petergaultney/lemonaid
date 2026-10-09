import pytest

from lemonaid.watch import briefs_events, briefs_orphans

from .shared import lemon, link

_TO = frozenset({"blocked", "merge", "done"})


@pytest.fixture
def live(monkeypatch):
    sessions = {"hq", "lead"}
    other: dict[str, set[str]] = {}
    monkeypatch.setattr(
        briefs_orphans,
        "live_sessions",
        lambda socket: frozenset(sessions) if socket == "" else frozenset(other.get(socket, ())),
    )
    return sessions, other


@pytest.fixture
def grove(live, tmp_path):
    hq, _ = lemon("hq", channel="codex:hq", session="hq")
    lead, _ = lemon("lead", channel="codex:lead", session="lead")
    link(lead, hq)
    return hq, lead, tmp_path / "watch-state"


def _watch(grove, to=_TO):
    return briefs_events.open_watch(grove[2], grove[0], "me", 0, to, orphans=True)


def _poll(w):
    sent = []
    briefs_events.poll(w, sent.append)
    return sent


def _set(path, before, after):
    path.write_text(path.read_text().replace(f"Status: {before}", f"Status: {after}"))


def test_unparented_brief_is_watched(grove):
    w = _watch(grove)
    loner, path = lemon("loner", channel="codex:loner", session="loner")
    assert _poll(w) == []
    _set(path, "working", "blocked")
    assert _poll(w) == [f"{loner}: Status: working -> blocked ({path})"]


def test_brief_with_a_live_parent_is_ignored(grove):
    _, lead, _ = grove
    w = _watch(grove)
    owned, path = lemon("owned", channel="codex:owned", session="owned")
    link(owned, lead)
    _set(path, "working", "blocked")
    assert _poll(w) == []


def test_brief_whose_parent_session_is_gone_is_watched(grove, live):
    _, lead, _ = grove
    owned, path = lemon("owned", channel="codex:owned", session="owned")
    link(owned, lead)
    w = _watch(grove)
    live[0].discard("lead")
    _set(path, "working", "done")
    assert _poll(w) == [f"{owned}: Status: done ({path})"]


def test_needs_ask_wakes_in_orphans_mode_without_a_status_change(grove):
    w = _watch(grove)
    loner, path = lemon("loner", channel="codex:loner", session="loner")
    assert _poll(w) == []
    path.write_text(
        path.read_text().replace("### Needs Peter\n\n", "### Needs Peter\n\n- decide\n")
    )
    assert _poll(w) == [f"{loner}: Status: working; Needs: decide ({path})"]


def test_status_outside_to_does_not_wake(grove):
    w = _watch(grove)
    _, path = lemon("loner", channel="codex:loner", session="loner")
    _set(path, "working", "waiting")
    assert _poll(w) == []


def test_tmux_failure_keeps_parented_briefs_quiet(grove, monkeypatch):
    _, lead, _ = grove
    owned, path = lemon("owned", channel="codex:owned", session="owned")
    link(owned, lead)
    monkeypatch.setattr(briefs_orphans, "live_sessions", lambda socket: None)
    w = _watch(grove)
    _set(path, "working", "blocked")
    assert _poll(w) == []


def test_parent_on_another_tmux_server_is_checked_there(grove, live):
    lead, _ = lemon("remote", channel="codex:remote", session="remote", socket="/tmp/other")
    owned, path = lemon("owned", channel="codex:owned", session="owned")
    link(owned, lead)
    live[1]["/tmp/other"] = {"remote"}
    w = _watch(grove)
    _set(path, "working", "blocked")
    assert _poll(w) == []
    live[1]["/tmp/other"].discard("remote")
    assert _poll(w) == [f"{owned}: Status: blocked ({path})"]
