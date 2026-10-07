"""Where a cmux session is, for switching to it and for the watcher.

The rule is in cmux/navigation.py: the recorded surface while it keeps the
recorded tty, else a surface cmux bound the session to where its agent runs,
else (for a row recorded without a surface) the surface on its tty.
"""

import json
import logging
import subprocess

import pytest

from lemonaid import handlers
from lemonaid.cmux import navigation
from lemonaid.config import Config
from lemonaid.inbox import db, unarchive
from lemonaid.lemon_watchers import watcher
from lemonaid.lemon_watchers.common import detect_terminal_switch_source

S1 = navigation.Surface("W1", "WS1", "S1")
S3 = navigation.Surface("W1", "WS2", "S3")

_TREE = {
    "windows": [
        {
            "id": "W1",
            "workspaces": [
                {
                    "id": "WS1",
                    "panes": [{"surfaces": [{"id": "S1", "tty": "ttys001", "type": "terminal"}]}],
                },
                {
                    "id": "WS2",
                    "panes": [
                        {"surfaces": [{"id": "S2", "tty": None, "type": "browser"}]},
                        {"surfaces": [{"id": "S3", "tty": "ttys002", "type": "terminal"}]},
                    ],
                },
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def _fresh_module_state(monkeypatch):
    monkeypatch.setattr(navigation, "_swept", None)
    monkeypatch.setattr(navigation, "_answering", True)


class _FakeCmux:
    """Answers `tree` and `list-panels`; `bindings` is {workspace: {surface: session}}."""

    def __init__(self) -> None:
        self.bindings: dict[str, dict[str, str]] = {"WS1": {}, "WS2": {}}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str, timeout: float = 5) -> str:
        self.calls.append(args)
        if "tree" in args:
            return json.dumps(_TREE)
        if "list-panels" in args:
            workspace = args[args.index("--workspace") + 1]
            return json.dumps(
                {
                    "surfaces": [
                        {"id": surface, "resume_binding": {"checkpoint_id": session}}
                        for surface, session in self.bindings[workspace].items()
                    ]
                }
            )
        return "OK"

    def ran(self, command: str) -> int:
        return sum(1 for call in self.calls if command in call)


@pytest.fixture
def cmux(monkeypatch):
    fake = _FakeCmux()
    monkeypatch.setattr(navigation, "_cmux", fake)
    return fake


def _runs_on(*ttys: str):
    return lambda metadata, tty: tty in ttys


def _row(**metadata):
    return {"channel": "claude:sess-a", "session_id": "sess-a", **metadata}


# The rule


def test_the_recorded_surface_with_its_tty_needs_no_sweep(cmux):
    found = navigation.locate(_row(cmux_surface="S3", tty="/dev/ttys002"), _runs_on())

    assert found == S3
    assert cmux.ran("list-panels") == 0


def test_a_reused_tty_is_not_the_session(cmux):
    """S3 now has the tty the session had on a surface that is gone."""
    found = navigation.locate(_row(cmux_surface="S9", tty="/dev/ttys002"), _runs_on("/dev/ttys002"))

    assert found is None


def test_a_reused_surface_is_not_the_session(cmux):
    """The recorded surface is there with another tty, and cmux binds the session nowhere."""
    found = navigation.locate(_row(cmux_surface="S3", tty="/dev/ttys009"), _runs_on("/dev/ttys002"))

    assert found is None


def test_a_session_cmux_resumed_elsewhere_is_found_by_its_binding(cmux):
    """After a cmux restart, the recorded surface and tty are both stale."""
    cmux.bindings["WS2"] = {"S3": "sess-a"}

    found = navigation.locate(_row(cmux_surface="S9", tty="/dev/ttys009"), _runs_on("/dev/ttys002"))

    assert found == S3


def test_a_binding_whose_agent_exited_does_not_count(cmux):
    cmux.bindings["WS2"] = {"S3": "sess-a"}

    assert navigation.locate(_row(cmux_surface="S9", tty="/dev/ttys009"), _runs_on()) is None


def test_a_session_running_on_two_surfaces_is_ambiguous(cmux):
    cmux.bindings = {"WS1": {"S1": "sess-a"}, "WS2": {"S3": "sess-a"}}
    found = navigation.locate(
        _row(cmux_surface="S9", tty="/dev/ttys009"), _runs_on("/dev/ttys001", "/dev/ttys002")
    )

    assert found == navigation.AMBIGUOUS


def test_ps_failing_is_unknown(cmux):
    cmux.bindings["WS2"] = {"S3": "sess-a"}
    found = navigation.locate(_row(cmux_surface="S9", tty="/dev/ttys009"), lambda m, t: None)

    assert found == navigation.UNKNOWN


def test_a_row_recorded_without_a_surface_falls_back_to_its_tty(cmux):
    assert navigation.locate(_row(tty="/dev/ttys002"), _runs_on()) == S3


# Asking cmux


def test_queries_use_a_sub_second_timeout(monkeypatch):
    seen = []

    def run(argv, **kwargs):
        seen.append(kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_TREE), stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    navigation.locate(_row(cmux_surface="S1", tty="/dev/ttys001"), _runs_on())

    assert seen == [navigation._QUERY_TIMEOUT_SECONDS]
    assert navigation._QUERY_TIMEOUT_SECONDS < 1


def test_cmux_not_answering_is_logged_once_until_it_answers(monkeypatch, caplog):
    answering = False

    def fake(*args, timeout=5):
        if not answering:
            raise subprocess.TimeoutExpired(["cmux", *args], timeout)
        return json.dumps(_TREE)

    monkeypatch.setattr(navigation, "_cmux", fake)
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            with pytest.raises(navigation.CmuxUnavailable):
                navigation.locate(_row(cmux_surface="S1", tty="/dev/ttys001"), _runs_on())
        answering = True
        navigation.locate(_row(cmux_surface="S1", tty="/dev/ttys001"), _runs_on())

    messages = [r.getMessage() for r in caplog.records]
    assert len([m for m in messages if "stopped answering" in m]) == 1
    assert len([m for m in messages if "answering again" in m]) == 1


# The watcher's question


def test_where_answers_each_session_from_one_tree(cmux):
    cmux.bindings["WS2"] = {"S3": "sess-b"}
    answers = navigation.where(
        [
            _row(channel="claude:here", cmux_surface="S1", tty="/dev/ttys001"),
            _row(channel="claude:moved", session_id="sess-b", cmux_surface="S9", tty="/dev/x"),
            _row(channel="claude:gone", session_id="sess-c", cmux_surface="S8", tty="/dev/y"),
        ],
        _runs_on("/dev/ttys002"),
    )

    assert answers == {
        "claude:here": "/dev/ttys001",
        "claude:moved": "/dev/ttys002",
        "claude:gone": False,
    }
    assert cmux.ran("tree") == 1


def test_where_reuses_a_recent_sweep_but_a_switch_does_not(cmux):
    moved = _row(cmux_surface="S9", tty="/dev/ttys009")
    navigation.where([moved], _runs_on())
    navigation.where([moved], _runs_on())
    assert cmux.ran("list-panels") == 2  # one sweep: a call per workspace

    navigation.locate(moved, _runs_on())
    assert cmux.ran("list-panels") == 4


def test_where_is_unknown_when_cmux_does_not_answer(monkeypatch):
    def fail(*args, timeout=5):
        raise subprocess.CalledProcessError(1, ["cmux", *args])

    monkeypatch.setattr(navigation, "_cmux", fail)

    assert navigation.where([_row(tty="/dev/ttys001")], _runs_on()) == {"claude:sess-a": None}


def test_only_per_session_sources_are_asked(cmux):
    answers = handlers.where_sessions_are(
        [
            ("tmux", _row(channel="claude:t", tty="/dev/ttys001")),
            ("cmux", _row(tty="/dev/ttys001")),
        ]
    )

    assert list(answers) == ["claude:sess-a"]


def _watcher_row(tty: str) -> tuple:
    return ("claude:a", "s", "/work/feat", 1.0, False, tty, "", "cmux")


def test_the_watcher_archives_a_session_that_is_gone(monkeypatch):
    archived: list[str] = []
    watcher._archive_stale_sessions(
        [_watcher_row("/dev/ttys001")], archived.append, {}, {}, located={"claude:a": False}
    )

    assert archived == ["claude:a"]


def test_the_watcher_judges_a_moved_session_on_its_current_tty(monkeypatch):
    """Its recorded tty has no agent on it any more; the tty it moved to does."""
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: tty == "/dev/new")
    archived: list[str] = []
    watcher._archive_stale_sessions(
        [_watcher_row("/dev/old")], archived.append, {}, {}, located={"claude:a": "/dev/new"}
    )

    assert archived == []


def test_the_watcher_keeps_a_session_its_backend_could_not_place(monkeypatch):
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)
    archived: list[str] = []
    watcher._archive_stale_sessions(
        [_watcher_row("/dev/ttys001")], archived.append, {}, {}, located={"claude:a": None}
    )

    assert archived == []


# Switching


def test_a_notification_focuses_its_surface(cmux):
    metadata = _row(cmux_surface="S3", tty="/dev/ttys002")

    assert handlers.handle_notification(metadata, Config(), switch_source="cmux") is True
    assert cmux.calls[-1] == (
        "focus-panel",
        "--panel",
        "S3",
        "--workspace",
        "WS2",
        "--window",
        "W1",
    )


def test_an_ambiguous_session_is_neither_switched_to_nor_recreated(cmux, monkeypatch):
    cmux.bindings = {"WS1": {"S1": "sess-a"}, "WS2": {"S3": "sess-a"}}
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: True)

    metadata = _row(cmux_surface="S9", tty="/dev/ttys009", cwd="/")
    assert handlers.handle_notification(metadata, Config(), switch_source="cmux") is False
    assert cmux.ran("focus-panel") == cmux.ran("new-workspace") == 0


def test_ps_failing_is_neither_a_switch_nor_a_recreate(cmux, monkeypatch):
    cmux.bindings["WS2"] = {"S3": "sess-a"}
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: None)

    metadata = _row(cmux_surface="S9", tty="/dev/ttys009", cwd="/")
    assert handlers.handle_notification(metadata, Config(), switch_source="cmux") is False
    assert cmux.ran("focus-panel") == cmux.ran("new-workspace") == 0


def test_a_dead_session_is_resumed_in_a_new_workspace(cmux, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: False)
    metadata = _row(cmux_surface="S9", tty="/dev/ttys009", cwd=str(tmp_path), name="feat")

    assert handlers.handle_notification(metadata, Config(), switch_source="cmux") is True
    created = cmux.calls[-1]
    assert created[0] == "new-workspace"
    assert created[created.index("--cwd") + 1] == str(tmp_path)
    assert created[created.index("--name") + 1] == "feat"
    assert "sess-a" in created[created.index("--command") + 1]


def test_a_gone_session_with_no_directory_does_nothing(cmux, monkeypatch):
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: False)
    metadata = _row(cmux_surface="S9", tty="/dev/ttys009")

    assert handlers.handle_notification(metadata, Config(), switch_source="cmux") is False
    assert cmux.ran("focus-panel") == cmux.ran("new-workspace") == 0


# Restoring from history


def _archived(**metadata) -> db.Notification:
    with db.connect() as conn:
        n = db.add(conn, "claude:sess-a", "waiting", metadata={"session_id": "sess-a", **metadata})
        conn.execute(
            "UPDATE notifications SET status = 'archived', switch_source = 'cmux' WHERE id = ?",
            (n.id,),
        )
        conn.commit()
        found = db.get(conn, n.id)
    assert found
    return found


def test_history_restores_a_session_cmux_resumed_on_a_new_tty(cmux, monkeypatch):
    """Resuming it instead would start a second copy of a running session."""
    cmux.bindings["WS2"] = {"S3": "sess-a"}
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: tty == "/dev/ttys002")
    monkeypatch.setattr(
        watcher, "is_process_running_on_tty", lambda tty, name: tty == "/dev/ttys002"
    )

    assert unarchive.running(_archived(cmux_surface="S9", tty="/dev/ttys009")) is True


def test_history_restores_a_session_running_on_two_surfaces(cmux, monkeypatch):
    cmux.bindings = {"WS1": {"S1": "sess-a"}, "WS2": {"S3": "sess-a"}}
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: True)
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)

    assert unarchive.running(_archived(cmux_surface="S9", tty="/dev/ttys009")) is True


def test_history_resumes_a_session_in_no_surface(cmux, monkeypatch):
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: False)

    assert unarchive.running(_archived(cmux_surface="S9", tty="/dev/ttys009")) is False


def test_history_resumes_a_session_whose_agent_left_its_surface(cmux, monkeypatch):
    """The surface and tty still match, but only a shell runs there now."""
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: False)

    assert unarchive.running(_archived(cmux_surface="S3", tty="/dev/ttys002")) is False


def test_history_does_not_trust_a_watcher_sweep(cmux, monkeypatch):
    monkeypatch.setattr(watcher, "process_on_tty", lambda tty, name: False)
    moved = _row(cmux_surface="S9", tty="/dev/ttys009")
    navigation.where([moved], _runs_on())
    swept = cmux.ran("list-panels")

    unarchive.running(_archived(cmux_surface="S9", tty="/dev/ttys009"))

    assert cmux.ran("list-panels") == 2 * swept


def test_a_cmux_tty_alone_says_nothing_about_its_session():
    """No caller may archive or resume a cmux session on its recorded tty alone."""
    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "cmux") is None


# Recording


def test_the_surface_survives_an_observation_that_could_not_see_it():
    with db.connect() as conn:
        db.add(
            conn, channel="claude:a", message="m", metadata={"tty": "/dev/t", "cmux_surface": "S1"}
        )
        db.add(conn, channel="claude:a", message="m", metadata={"tty": "/dev/t"})
        found = db.get_by_channel(conn, "claude:a", unread_only=False)

    assert found.metadata["cmux_surface"] == "S1"


def test_cmux_is_detected_from_its_surface_variable(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    monkeypatch.setenv("CMUX_SURFACE_ID", "S1")

    assert detect_terminal_switch_source() == "cmux"


def test_tmux_inside_cmux_is_navigated_by_tmux(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")
    monkeypatch.setenv("CMUX_SURFACE_ID", "S1")

    assert detect_terminal_switch_source() == "tmux"
