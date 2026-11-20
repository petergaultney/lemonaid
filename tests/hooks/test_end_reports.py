"""Whether a harness reports its quits to lemonaid, read from its own settings."""

import json

import pytest

from lemonaid.claude import install_hooks
from lemonaid.codex import hook_trust
from lemonaid.hooks import end_reports, install

_REPORTED = end_reports.reported


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setattr(install_hooks, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(end_reports, "_CLAUDE_MANAGED", tmp_path / "managed.json")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    (tmp_path / "codex").mkdir()
    return tmp_path


def test_claude_reports_once_its_session_end_hook_is_installed(homes):
    assert not _REPORTED("claude", "")

    install.install("claude", events=["SessionEnd"])

    assert _REPORTED("claude", "")


@pytest.mark.parametrize("where", ["settings.json", "project/.claude/settings.local.json"])
def test_claude_with_hooks_disabled_reports_nothing(homes, where):
    install.install("claude", events=["SessionEnd"])
    settings = homes / where
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps({**json.loads(settings.read_text() or "{}"), "disableAllHooks": True})
        if settings.exists()
        else json.dumps({"disableAllHooks": True})
    )

    assert not _REPORTED("claude", str(homes / "project"))


class _Codex:
    """An app-server answering `hooks/list` with *hooks*."""

    def __init__(self, hooks: list[dict]) -> None:
        self.hooks = hooks

    def ask(self, calls, timeout):
        assert [method for method, _ in calls] == ["hooks/list"]
        return [{"result": {"data": [{"cwd": "/", "hooks": self.hooks}]}}]


@pytest.fixture
def codex_hooks(homes, monkeypatch):
    """Set what Codex says about the hooks it would run; lemonaid's daemon check passes."""
    hook_trust._runs.cache_clear()
    (homes / "codex" / "config.toml").write_text("[features]\ndaemon_auto_start = false\n")
    answers = _Codex([])
    monkeypatch.setattr(
        hook_trust.app_server,
        "once",
        lambda question, about, unanswered, timeout: question(answers),
    )

    def hooks(**fields) -> None:
        hook_trust._runs.cache_clear()
        answers.hooks = [
            {
                "eventName": "sessionEnd",
                "sourcePath": str(install.settings_path("codex")),
                "statusMessage": install.status_message("session-end"),
                "enabled": True,
                "trustStatus": "trusted",
                **fields,
            }
        ]

    return hooks


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, True),
        ({"trustStatus": "modified"}, False),
        ({"trustStatus": "untrusted"}, False),
        ({"enabled": False}, False),
        ({"statusMessage": "my own end"}, False),
        ({"eventName": "stop"}, False),
    ],
)
def test_codex_reports_only_with_lemonaids_hook_trusted_and_enabled(codex_hooks, fields, expected):
    install.install("codex", events=["SessionEnd"])
    codex_hooks(**fields)

    assert _REPORTED("codex", "") is expected


def test_codex_with_its_daemon_on_reports_nothing(homes, codex_hooks):
    install.install("codex", events=["SessionEnd"])
    codex_hooks()
    (homes / "codex" / "config.toml").write_text("[features]\ndaemon_auto_start = true\n")

    assert not _REPORTED("codex", "")


def test_other_harnesses_never_report(homes):
    assert not _REPORTED("opencode", "")


def test_codex_that_could_not_be_asked_is_asked_again(homes, codex_hooks, monkeypatch):
    install.install("codex", events=["SessionEnd"])
    codex_hooks()
    healthy = hook_trust.app_server.once
    monkeypatch.setattr(
        hook_trust.app_server, "once", lambda question, about, unanswered, timeout: unanswered
    )
    assert not _REPORTED("codex", "")

    monkeypatch.setattr(hook_trust.app_server, "once", healthy)
    assert _REPORTED("codex", "")
