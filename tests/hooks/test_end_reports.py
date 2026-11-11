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


def _trust(home, state: str) -> None:
    hooks = home / "codex" / "hooks.json"
    [handler] = [
        handler
        for entry in json.loads(hooks.read_text())["hooks"]["SessionEnd"]
        for handler in entry["hooks"]
    ]
    trusted = {
        "trusted": hook_trust._session_end_hash(handler),
        "stale": hook_trust._session_end_hash({**handler, "timeout": 2}),
        "disabled": hook_trust._session_end_hash(handler),
    }[state]
    (home / "codex" / "config.toml").write_text(
        "[features]\ndaemon_auto_start = false\n\n"
        f'[hooks.state."{hooks}:session_end:0:0"]\ntrusted_hash = "{trusted}"\n'
        + ("enabled = false\n" if state == "disabled" else "")
    )


@pytest.mark.parametrize(
    ("state", "expected"), [("trusted", True), ("stale", False), ("disabled", False)]
)
def test_codex_reports_only_with_its_own_hook_trusted_at_its_hash_and_enabled(
    homes, state, expected
):
    install.install("codex", events=["SessionEnd"])
    _trust(homes, state)

    assert _REPORTED("codex", "") is expected


def test_codex_trust_for_another_session_end_hook_is_not_lemonaids(homes):
    hooks = homes / "codex" / "hooks.json"
    mine = {"type": "command", "command": "my-own-end"}
    hooks.write_text(json.dumps({"hooks": {"SessionEnd": [{"hooks": [mine]}]}}))
    install.install("codex", events=["SessionEnd"])
    (homes / "codex" / "config.toml").write_text(
        "[features]\ndaemon_auto_start = false\n\n"
        f'[hooks.state."{hooks}:session_end:0:0"]\n'
        f'trusted_hash = "{hook_trust._session_end_hash(mine)}"\n'
    )

    assert not _REPORTED("codex", "")


def test_codex_with_its_daemon_on_reports_nothing(homes):
    install.install("codex", events=["SessionEnd"])
    _trust(homes, "trusted")
    config = homes / "codex" / "config.toml"
    config.write_text(
        config.read_text().replace("daemon_auto_start = false", "daemon_auto_start = true")
    )

    assert not _REPORTED("codex", "")


_CODEX_TRUSTED = "sha256:9f9337c92115356e7107de78bbcec70d6b5888a1d8312033ae4c21053efb7b91"
# What Codex 0.166 wrote to `[hooks.state]` when this handler was trusted in its `/hooks`.


def test_the_trust_hash_is_codexs():
    handler = {
        "type": "command",
        "command": install.SESSION_END_CODEX,
        "statusMessage": "lemonaid: session-end",
        "timeout": 3,
    }

    assert hook_trust._session_end_hash(handler) == _CODEX_TRUSTED


def test_other_harnesses_never_report(homes):
    assert not _REPORTED("opencode", "")
