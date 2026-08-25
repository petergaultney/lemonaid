"""The report that says what a crash would cost, before the crash.

Restore depends on facts recorded long before they are needed, and every way it
can fail is silent: a missing window, a session id whose transcript is gone, a
hook that was never installed. These pin that each of those is reported rather
than discovered afterwards.
"""


from lemonaid.inbox import db, doctor


def _session(**metadata) -> None:
    with db.connect() as conn:
        db.add(conn, f"claude:{metadata.get('session_id', 'x')}", "m", "a-session", metadata)


def test_a_session_without_a_transcript_is_not_restorable(monkeypatch):
    """Resuming this one starts a fresh conversation - the failure that reads
    like success, because `claude --resume` on a missing id does not complain."""
    monkeypatch.setattr(doctor, "transcript_for", lambda sid: None)

    ok, why = doctor._restorable({"session_id": "abc", "cwd": "/tmp"})
    assert not ok
    assert "transcript" in why


def test_a_session_without_an_id_is_not_restorable():
    ok, why = doctor._restorable({"cwd": "/tmp"})
    assert not ok
    assert "session_id" in why


def test_a_session_without_a_cwd_is_not_restorable():
    ok, why = doctor._restorable({"session_id": "abc"})
    assert not ok
    assert "cwd" in why


def test_a_complete_session_is_restorable(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "transcript_for", lambda sid: tmp_path / "t.jsonl")

    ok, _ = doctor._restorable(
        {"session_id": "abc", "cwd": "/tmp", "tmux_session": "relay", "tmux_window": "2"}
    )
    assert ok


def test_a_session_with_no_window_restores_but_is_not_placed(monkeypatch, tmp_path):
    """It comes back, just not where it was - worth saying, not worth refusing."""
    monkeypatch.setattr(doctor, "transcript_for", lambda sid: tmp_path / "t.jsonl")

    ok, why = doctor._restorable({"session_id": "abc", "cwd": "/tmp"})
    assert ok
    assert "not be placed" in why


def test_claude_panes_are_recognised_by_their_version_title():
    """Claude Code names its process after its own version, so there is no name
    to match on."""
    assert doctor._looks_like_a_lemon("2.1.245")
    assert doctor._looks_like_a_lemon("claude")
    assert doctor._looks_like_a_lemon("codex")


def test_a_shell_is_not_a_lemon():
    for command in ("xonsh", "bash", "python3.14", "emacsclient", "k9s"):
        assert not doctor._looks_like_a_lemon(command), command


def test_the_report_counts_running_panes_the_inbox_missed(monkeypatch):
    """The number that mattered this morning: 20 running, 8 known."""
    monkeypatch.setattr(
        doctor,
        "live_panes",
        lambda: [
            doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245"),
            doctor.Pane("hq", "1", "/dev/ttys002", "2.1.245"),
            doctor.Pane("hq", "3", "/dev/ttys003", "xonsh"),
        ],
    )
    _session(session_id="abc", cwd="/tmp", tty="/dev/ttys001")

    report = "\n".join(doctor.report())
    assert "2 agent panes running" in report
    assert "1 running panes the inbox does not know about" in report


def test_unknown_panes_lists_only_agents_with_no_row(monkeypatch):
    monkeypatch.setattr(
        doctor,
        "live_panes",
        lambda: [
            doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245"),
            doctor.Pane("hq", "1", "/dev/ttys002", "2.1.245"),
            doctor.Pane("hq", "3", "/dev/ttys003", "xonsh"),
        ],
    )
    _session(session_id="abc", cwd="/tmp", tty="/dev/ttys001")

    assert [p.tty for p in doctor.unknown_panes()] == ["/dev/ttys002"]
