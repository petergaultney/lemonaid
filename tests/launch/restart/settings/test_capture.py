import pytest

from lemonaid.launch.restart import settings


def test_native_model_selection_wins_over_original_launch_model(monkeypatch):
    monkeypatch.setattr(
        settings.launch_args,
        "argv",
        lambda pid: ["claude", "--model", "sonnet", "--dangerously-skip-permissions"],
    )
    observed = settings.capture(
        "claude", 123, {"model": "claude-opus-4-7", "permission_mode": "default"}, {}
    )
    assert observed["model"] == "claude-opus-4-7"
    assert observed["permission"] == "default"


def test_missing_effective_settings_are_refused(monkeypatch):
    monkeypatch.setattr(settings.launch_args, "argv", lambda pid: ["codex", "--no-daemon"])
    with pytest.raises(ValueError, match="model"):
        settings.capture("codex", 123, {}, {})


def test_codex_discards_only_its_per_process_path_and_deduplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings.launch_args,
        "argv",
        lambda pid: ["codex", "--no-daemon", "-s", "read-only", "-a", "on-request"],
    )
    home = tmp_path / "codex"
    dynamic = home / "tmp/arg0/codex-arg0new"
    data = {"model": "gpt-6", "effort": "high", "model_provider": "openai"}
    captured = settings.capture(
        "codex",
        123,
        data,
        {"CODEX_HOME": str(home), "PATH": f"{dynamic}:/target/bin:/target/bin:/usr/bin"},
    )
    assert captured["environment"]["PATH"] == "/target/bin:/usr/bin"
    assert captured["environment"]["CODEX_HOME"] == str(home)
