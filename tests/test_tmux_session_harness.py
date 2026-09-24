"""Choosing a configured harness when a tmux session is created."""

from lemonaid.config import TmuxSessionConfig
from lemonaid.tmux import session


def _created_sessions(monkeypatch) -> list[dict]:
    created: list[dict] = []
    monkeypatch.setattr(
        session,
        "create_session",
        lambda **kwargs: created.append(kwargs) or True,
    )
    return created


def test_spawn_session_selects_a_named_harness_template(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={
            "default": ["editor", "claude", ""],
            "codex": ["editor", "codex", ""],
        }
    )

    assert (
        session.spawn_session(
            str(tmp_path),
            config,
            session_name="work",
            template_name="codex",
            attach=False,
        )
        is None
    )

    assert created[0]["windows"] == ["editor", "codex", ""]


def test_spawn_session_shell_quotes_prompt_on_the_harness_command(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"codex": ["editor", "codex", ""]},
        resume_window=1,
    )

    assert (
        session.spawn_session(
            str(tmp_path),
            config,
            session_name="work",
            template_name="codex",
            initial_prompt="read Peter's brief; then go",
            attach=False,
        )
        is None
    )

    assert created[0]["windows"] == [
        "editor",
        "codex 'read Peter'\"'\"'s brief; then go'",
        "",
    ]


def test_prompt_can_target_a_window_other_than_resume(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"other": ["harness", "editor"]},
        resume_window=1,
        harness_window=0,
    )

    session.spawn_session(
        str(tmp_path),
        config,
        session_name="work",
        template_name="other",
        initial_prompt="start here",
        attach=False,
    )

    assert created[0]["windows"] == ["harness 'start here'", "editor"]


def test_unknown_harness_template_is_an_error(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)

    error = session.spawn_session(
        str(tmp_path),
        TmuxSessionConfig(templates={"default": ["claude"]}),
        session_name="work",
        template_name="codex",
        attach=False,
    )

    assert error == "No tmux-session template 'codex' in config"
    assert not created


def test_prompt_requires_a_command_in_the_harness_window(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)

    error = session.spawn_session(
        str(tmp_path),
        TmuxSessionConfig(templates={"empty": ["editor", ""]}, resume_window=1),
        session_name="work",
        template_name="empty",
        initial_prompt="do something",
        attach=False,
    )

    assert error == "Tmux-session template 'empty' has no harness command in window 1"
    assert not created
