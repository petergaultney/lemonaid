"""The report that says what a crash would cost, before the crash.

Restore depends on facts recorded long before they are needed, and every way it
can fail is silent: a missing window, a session id whose transcript is gone, a
hook that was never installed. These pin that each of those is reported rather
than discovered afterwards.
"""

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db, doctor


def _session(**metadata) -> None:
    with db.connect() as conn:
        db.add(conn, f"claude:{metadata.get('session_id', 'x')}", "m", "a-session", metadata)


def _row(*, channel: str = "claude:abc", **metadata) -> db.Notification:
    return db.Notification(id=1, channel=channel, message="m", metadata=metadata)


def test_a_session_without_a_transcript_is_not_restorable():
    """Resuming this one starts a fresh conversation - the failure that reads
    like success, because `claude --resume` on a missing id does not complain."""
    ok, why = doctor._restorable(_row(session_id="abc", cwd="/tmp"), Config(), {"claude:abc"})
    assert not ok
    assert "transcript" in why


@pytest.mark.parametrize("suffix", [".jsonl", ".jsonl.zst"])
def test_a_codex_session_with_its_rollout_on_disk_is_restorable(monkeypatch, tmp_path, suffix):
    """Codex keeps its transcripts under its own home, not Claude's projects, and
    compresses idle ones, which it still resumes."""
    thread = "01a1d2dd-f50b-7321-8f79-c76783f22ada"
    rollout = tmp_path / f".codex/sessions/2026/11/12/rollout-2026-11-12T22-05-24-{thread}{suffix}"
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    monkeypatch.setenv("HOME", str(tmp_path))

    row = _row(channel=f"codex:{thread}", session_id=thread, cwd="/tmp", tmux_session="krc-ua")
    ok, why = doctor._restorable(row, Config(), doctor.transcript.missing([row]))

    assert (ok, why) == (True, "restorable")


@pytest.mark.parametrize(
    "channel",
    [
        "lemonaid:example",  # no harness resumes it
        "openclaw:example",  # its resume command needs a session_key this row lacks
    ],
)
def test_a_session_with_no_resume_command_is_not_restorable(channel):
    """Restore can't start what it has no resume line for, whatever is on disk."""
    ok, why = doctor._restorable(
        _row(channel=channel, session_id="example", cwd="/tmp", tmux_session="t"), Config(), set()
    )

    assert (ok, why) == (False, "no resume command for its harness")


def test_a_session_without_an_id_is_not_restorable():
    ok, why = doctor._restorable(_row(cwd="/tmp"), Config(), set())
    assert not ok
    assert "session_id" in why


def test_a_session_without_a_cwd_is_not_restorable():
    ok, why = doctor._restorable(_row(session_id="abc"), Config(), set())
    assert not ok
    assert "cwd" in why


def test_a_complete_session_is_restorable():
    ok, _ = doctor._restorable(
        _row(session_id="abc", cwd="/tmp", tmux_session="relay", tmux_window="2"), Config(), set()
    )
    assert ok


def test_a_session_with_no_window_restores_but_is_not_placed():
    """It comes back, just not where it was - worth saying, not worth refusing."""
    ok, why = doctor._restorable(_row(session_id="abc", cwd="/tmp"), Config(), set())
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


def _panes(monkeypatch, panes, cwds):
    monkeypatch.setattr(doctor, "live_panes", lambda: panes)
    monkeypatch.setattr(doctor, "_pane_cwd", lambda p: cwds.get(p))


def test_adoption_matches_a_pane_to_its_conversation(monkeypatch):
    pane = doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")
    _panes(monkeypatch, [pane], {pane: "/work/a"})
    monkeypatch.setattr(doctor, "_newest_transcript_for", lambda cwd: ("sid-a", 100.0))

    plans = doctor.plan_adoption()
    assert [(p.session_id, p.contested) for p in plans] == [("sid-a", False)]


def test_two_panes_in_one_directory_are_guesses(monkeypatch):
    """Nothing on disk records which pane a transcript belonged to."""
    a = doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")
    b = doctor.Pane("relay", "3", "/dev/ttys002", "2.1.245")
    _panes(monkeypatch, [a, b], {a: "/work/same", b: "/work/same"})
    monkeypatch.setattr(doctor, "_newest_transcript_for", lambda cwd: ("sid-x", 100.0))

    assert all(p.contested for p in doctor.plan_adoption())


def test_a_transcript_claimed_twice_is_a_guess(monkeypatch):
    """Distinct directories can still resolve to one conversation, which is not
    visible from either pane alone."""
    a = doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")
    b = doctor.Pane("hq", "1", "/dev/ttys002", "2.1.245")
    _panes(monkeypatch, [a, b], {a: "/work/a", b: "/work/b"})
    monkeypatch.setattr(doctor, "_newest_transcript_for", lambda cwd: ("sid-same", 100.0))

    assert all(p.contested for p in doctor.plan_adoption())


def test_a_conversation_already_in_the_inbox_makes_it_a_guess(monkeypatch):
    """It is demonstrably running somewhere else, so it is not this pane."""
    pane = doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")
    _panes(monkeypatch, [pane], {pane: "/work/a"})
    monkeypatch.setattr(doctor, "_newest_transcript_for", lambda cwd: ("sid-taken", 100.0))
    _session(session_id="sid-taken", cwd="/elsewhere", tty="/dev/ttys999")

    assert doctor.plan_adoption()[0].contested


def test_adopting_records_the_window(monkeypatch):
    """The point: an adopted session can then be placed by restore."""
    pane = doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")
    doctor.adopt([doctor.Adoption(pane, "/work/a", "sid-a", contested=False)])

    with db.connect() as conn:
        row = db.Notification.from_row(conn.execute("SELECT * FROM notifications").fetchone())
    assert (row.metadata["tmux_session"], row.metadata["tmux_window"]) == ("relay", "2")

    assert doctor._restorable(row, Config(), set()) == (True, "restorable")


def test_the_report_says_what_to_do(monkeypatch):
    monkeypatch.setattr(
        doctor,
        "live_panes",
        lambda: [doctor.Pane("relay", "2", "/dev/ttys001", "2.1.245")],
    )

    assert any("lemonaid tmux adopt" in line for line in doctor.report())
