import pytest

from lemonaid.config import BackendConfig, Config
from lemonaid.inbox import db
from lemonaid.launch.restart import settings

from .. import shared


def test_codex_resume_preserves_settings_without_adding_writable_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.shutil, "which", lambda name, **kwargs: "/upgraded/bin/" + name)
    source = {
        **shared.SETTINGS,
        "profile": "work",
        "argv": [
            *shared.SETTINGS["argv"],
            "-p",
            "work",
            "-c",
            'sandbox_workspace_write.writable_roots=["/chosen"]',
        ],
    }
    row = db.Notification(
        1, shared.CHANNEL, "", metadata={"session_id": shared.SESSION, "cwd": str(tmp_path)}
    )
    argv = settings.command(row, Config(), source)
    assert argv[:2] == ["/upgraded/bin/codex", "resume"]
    assert argv[-1] == shared.SESSION
    assert argv[argv.index("--profile") + 1] == "work"
    assert 'model_reasoning_effort="high"' in argv
    assert 'sandbox_workspace_write.writable_roots=["/chosen"]' in argv
    assert argv.count("--no-daemon") == 1
    assert str(db.get_db_path().parent) not in " ".join(argv)


@pytest.mark.parametrize(
    "command",
    [
        "codex resume {session_id} --model other",
        "codex resume {session_id} --sandbox danger-full-access",
        "wrapper codex resume {session_id}",
        "codex resume {session_id} && echo bad",
        "codex resume --last",
    ],
)
def test_conflicting_and_unverifiable_templates_are_refused(tmp_path, monkeypatch, command):
    monkeypatch.setattr(settings.shutil, "which", lambda name, **kwargs: name)
    row = db.Notification(
        1, shared.CHANNEL, "", metadata={"session_id": shared.SESSION, "cwd": str(tmp_path)}
    )
    config = Config(backends={"codex": BackendConfig(resume_command=command)})
    with pytest.raises(ValueError):
        settings.command(row, config, shared.SETTINGS)


def test_claude_wrapper_keeps_verified_cwd_and_exact_session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.shutil, "which", lambda name, **kwargs: name)
    row = db.Notification(
        1, "claude:01234567", "", metadata={"session_id": shared.SESSION, "cwd": str(tmp_path)}
    )
    source = {
        "model": "opus",
        "permission": "default",
        "argv": [
            "claude",
            "--model",
            "opus",
            "--permission-mode",
            "default",
            "--settings",
            '{"crossSessionInbound":"accept"}',
        ],
    }
    argv = settings.command(row, Config(), source)
    assert argv[0] == "claude"
    assert argv[-2:] == ["--resume", shared.SESSION]
    assert argv[argv.index("--settings") + 1] == '{"crossSessionInbound":"accept"}'
    assert argv[argv.index("--permission-mode") + 1] == "default"
