import json
from pathlib import Path

from lemonaid.claude import trust


def _config(tmp_path, projects):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"projects": projects}))
    return path


def test_a_trusted_directory_covers_those_below_it(tmp_path):
    config = _config(tmp_path, {"/work": {"hasTrustDialogAccepted": True}})
    assert trust.trusted(tmp_path / "x", config) is False
    assert trust.trusted(Path("/work/repo/sub"), config)


def test_a_project_recorded_without_trust_is_untrusted(tmp_path):
    config = _config(tmp_path, {"/work": {"hasTrustDialogAccepted": False}, "/other": {}})
    assert not trust.trusted(Path("/work"), config)
    assert not trust.trusted(Path("/other/x"), config)


def test_an_unreadable_config_trusts_nothing(tmp_path):
    assert not trust.trusted(tmp_path, tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{")
    assert not trust.trusted(tmp_path, tmp_path / "bad.json")


def test_the_config_follows_claude_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert trust.config_file() == tmp_path / ".claude.json"
