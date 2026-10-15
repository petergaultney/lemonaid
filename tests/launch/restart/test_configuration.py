import datetime as dt
import os
import time

import pytest

from lemonaid.launch.restart import configuration


def test_snapshot_rejects_configuration_changed_after_process_started(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model="chosen"')
    birth = dt.datetime.fromtimestamp(time.time() - 5).strftime("%a %b %d %H:%M:%S %Y")
    with pytest.raises(ValueError, match="changed after"):
        configuration.snapshot([path], birth)


def test_unchanged_covers_edits_deletions_and_new_files(tmp_path):
    path, absent = tmp_path / "settings.json", tmp_path / "local.json"
    path.write_text("{}")
    os.utime(path, (time.time() - 10, time.time() - 10))
    birth = dt.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    manifest = configuration.snapshot([path, absent], birth)
    configuration.unchanged(manifest)
    absent.write_text("{}")
    with pytest.raises(ValueError, match="configuration changed"):
        configuration.unchanged(manifest)
    absent.unlink()
    path.unlink()
    with pytest.raises(ValueError, match="configuration changed"):
        configuration.unchanged(manifest)


@pytest.mark.parametrize("equals", [False, True])
@pytest.mark.parametrize("change", ["add", "edit", "delete"])
def test_explicit_settings_files_are_guarded_in_both_forms(tmp_path, equals, change):
    custom = tmp_path / "custom.json"
    if change != "add":
        custom.write_text('{"permissions":{"deny":["Bash"]}}')
        os.utime(custom, (time.time() - 10, time.time() - 10))
    argv = ["claude", *(["--settings=custom.json"] if equals else ["--settings", "custom.json"])]
    paths = configuration.paths("claude", {}, str(tmp_path), "", argv)
    assert custom in paths
    manifest = configuration.snapshot(paths, dt.datetime.now().strftime("%a %b %d %H:%M:%S %Y"))
    if change == "delete":
        custom.unlink()
    else:
        custom.write_text('{"permissions":{"allow":["Bash"]}}')
    with pytest.raises(ValueError, match="configuration changed"):
        configuration.unchanged(manifest)
