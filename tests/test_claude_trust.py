import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from lemonaid.claude import trust


def _config(tmp_path, projects):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"projects": projects}))
    return path


def test_only_the_directory_s_own_entry_counts(tmp_path):
    config = _config(tmp_path, {"/work": {"hasTrustDialogAccepted": True}})
    assert trust.trusted(Path("/work"), config)
    assert not trust.trusted(Path("/work/cloned-repo"), config)


def test_a_project_recorded_without_trust_is_untrusted(tmp_path):
    config = _config(tmp_path, {"/work": {"hasTrustDialogAccepted": False}, "/other": {}})
    assert not trust.trusted(Path("/work"), config)
    assert not trust.trusted(Path("/other"), config)


def test_an_unreadable_config_trusts_nothing(tmp_path):
    assert not trust.trusted(tmp_path, tmp_path / "missing.json")
    (tmp_path / "bad.json").write_text("{")
    assert not trust.trusted(tmp_path, tmp_path / "bad.json")


def test_the_config_follows_claude_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert trust.config_file() == tmp_path / ".claude.json"


def test_a_grant_keeps_the_rest_of_the_config(tmp_path):
    config = tmp_path / ".claude.json"
    config.write_text(
        json.dumps({"theme": "dark", "projects": {"/work": {"history": [1], "x": 2}}})
    )
    config.chmod(0o600)
    trust.grant(Path("/work"), config)
    trust.grant(Path("/new"), config)
    data = json.loads(config.read_text())
    assert data["theme"] == "dark"
    assert data["projects"]["/work"] == {"history": [1], "x": 2, "hasTrustDialogAccepted": True}
    assert trust.trusted(Path("/new"), config)
    assert config.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [".claude.json"]


def test_concurrent_grants_all_survive(tmp_path):
    config = _config(tmp_path, {})
    grants = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; from lemonaid.claude import trust; "
                "trust.grant(Path(sys.argv[1]), Path(sys.argv[2]))",
                f"/destination-{n}",
                str(config),
            ]
        )
        for n in range(8)
    ]
    assert [grant.wait() for grant in grants] == [0] * 8
    assert all(trust.trusted(Path(f"/destination-{n}"), config) for n in range(8))


def test_a_grant_waits_for_claude_s_lock_and_keeps_its_save(tmp_path):
    config = _config(tmp_path, {})
    lock = tmp_path / ".claude.json.lock"
    lock.mkdir()
    granting = threading.Thread(target=trust.grant, args=(Path("/moved"), config))
    granting.start()
    time.sleep(0.3)
    assert granting.is_alive()
    config.write_text(json.dumps({"projects": {"/claude": {"hasTrustDialogAccepted": True}}}))
    lock.rmdir()
    granting.join(5)
    assert trust.trusted(Path("/moved"), config)
    assert trust.trusted(Path("/claude"), config)
    assert not lock.exists()


def test_an_abandoned_lock_is_taken_over(tmp_path):
    config = _config(tmp_path, {})
    lock = tmp_path / ".claude.json.lock"
    lock.mkdir()
    os.utime(lock, (time.time() - 60, time.time() - 60))
    trust.grant(Path("/moved"), config)
    assert trust.trusted(Path("/moved"), config)


def test_a_lock_that_stays_held_refuses_the_grant(tmp_path, monkeypatch):
    config = _config(tmp_path, {})
    (tmp_path / ".claude.json.lock").mkdir()
    monkeypatch.setattr(trust, "_WAIT_SECONDS", 0.2)
    with pytest.raises(TimeoutError):
        trust.grant(Path("/moved"), config)
    assert not trust.trusted(Path("/moved"), config)
