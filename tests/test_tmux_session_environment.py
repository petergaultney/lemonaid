"""A place identity reaches tmux before its harness starts."""

from lemonaid.config import TmuxSessionConfig
from lemonaid.tmux import session


class _Result:
    stdout = ""
    stderr = b""
    returncode = 0


def test_session_environment_is_set_before_the_harness_window_starts(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        session.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or _Result(),
    )
    monkeypatch.setattr(session, "get_base_index", lambda: 1)

    assert session.create_session(
        "work",
        ["", "codex"],
        directory=tmp_path,
        attach=False,
        environment={"LEMON_NAME": "Quokka"},
    )

    set_env = calls.index(["tmux", "set-environment", "-t", "work", "LEMON_NAME", "Quokka"])
    new_harness_window = calls.index(["tmux", "new-window", "-t", "work", "-c", str(tmp_path)])
    assert set_env < new_harness_window


def test_a_harness_in_the_first_window_gets_an_explicit_export(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        session.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or _Result(),
    )
    monkeypatch.setattr(session, "get_base_index", lambda: 0)

    session.create_session(
        "work",
        ["codex"],
        directory=tmp_path,
        attach=False,
        environment={"LEMON_NAME": "Peter's Quokka"},
    )

    assert [
        "tmux",
        "send-keys",
        "-t",
        "work:0",
        "export LEMON_NAME='Peter'\"'\"'s Quokka'; codex",
        "Enter",
    ] in calls


def test_recreated_session_recovers_the_places_existing_name(monkeypatch, tmp_path):
    created = []
    monkeypatch.setattr(
        "lemonaid.places.names.current_name",
        lambda directory: "Quokka",
    )
    monkeypatch.setattr(session, "create_session", lambda **kwargs: created.append(kwargs) or True)

    error = session.spawn_session(
        str(tmp_path),
        TmuxSessionConfig(templates={"default": ["codex"]}),
        session_name="work",
        attach=False,
    )

    assert error is None
    assert created[0]["environment"] == {"LEMON_NAME": "Quokka"}
