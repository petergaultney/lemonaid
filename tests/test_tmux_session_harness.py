"""Choosing a configured harness when a tmux session is created."""

import shlex
import subprocess

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


def test_spawn_session_passes_the_prompt_by_environment(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"default": ["editor", "claude", ""]},
        resume_window=1,
    )

    assert (
        session.spawn_session(
            str(tmp_path),
            config,
            session_name="work",
            template_name="default",
            initial_prompt="read Peter's brief; then go",
            attach=False,
        )
        is None
    )

    assert created[0]["windows"] == [
        "editor",
        'env -u LEMONAID_PROMPT claude "$LEMONAID_PROMPT"',
        "",
    ]
    assert created[0]["environments"] == [
        {},
        {"LEMONAID_PROMPT": "read Peter's brief; then go"},
        {},
    ]


def test_a_codex_harness_starts_past_its_trust_and_update_prompts(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"codex": ["editor", "codex --no-daemon"]}, resume_window=1
    )

    session.spawn_session(
        str(tmp_path), config, session_name="work", template_name="codex", attach=False
    )

    harness = created[0]["windows"][1]
    assert harness.startswith("codex -c ")
    assert f'{{"{tmp_path}"={{trust_level="trusted"}}}}' in harness
    assert "-c check_for_update_on_startup=false -c " in harness
    assert harness.endswith("--no-daemon")


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

    assert created[0]["windows"] == ['env -u LEMONAID_PROMPT harness "$LEMONAID_PROMPT"', "editor"]
    assert created[0]["environments"] == [{"LEMONAID_PROMPT": "start here"}, {}]


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


def test_rename_submits_with_configured_composer_key(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(session, "get_base_index", lambda: 0)
    monkeypatch.setattr(session.time, "sleep", lambda _: None)

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(session.subprocess, "run", run)

    assert session.create_session(
        "test",
        ["claude"],
        directory=tmp_path,
        claude_rename=True,
        claude_submit_key="C-Enter",
        attach=False,
    )

    assert ["tmux", "send-keys", "-t", "test:0", "claude", "Enter"] in calls
    assert ["tmux", "send-keys", "-t", "test:0", "/rename test"] in calls
    assert [
        "tmux",
        "send-keys",
        "-t",
        "test:0",
        "-H",
        "1b",
        "5b",
        "31",
        "33",
        "3b",
        "35",
        "75",
    ] in calls


def test_a_new_codex_session_can_write_the_configured_roots(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"codex": ["editor", "codex --no-daemon"]},
        resume_window=1,
        codex_writable_roots=(tmp_path / "reviews",),
    )

    session.spawn_session(
        str(tmp_path), config, session_name="work", template_name="codex", attach=False
    )

    words = shlex.split(created[0]["windows"][1])
    assert any(
        w.startswith("sandbox_workspace_write.writable_roots=") and str(tmp_path / "reviews") in w
        for w in words
    )


def test_a_resumed_codex_session_can_write_the_configured_roots(monkeypatch, tmp_path):
    created = _created_sessions(monkeypatch)
    config = TmuxSessionConfig(
        templates={"codex": ["editor", "codex --no-daemon"]},
        resume_window=1,
        codex_writable_roots=(tmp_path / "reviews",),
    )

    session.spawn_session(
        str(tmp_path),
        config,
        resume_argv=["codex", "resume", "abc"],
        session_name="work",
        template_name="codex",
        attach=False,
    )

    words = shlex.split(created[0]["windows"][1])
    assert words[-2:] == ["resume", "abc"]
    assert any(w.startswith("sandbox_workspace_write.writable_roots=") for w in words)
