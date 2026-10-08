import argparse
import json
import shlex
import shutil
import subprocess
import uuid

import pytest

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership, target, toss_cli, workspace_purpose


def _workspace(
    monkeypatch, tmp_path, *, owner_lookup="echo {dir}", cd_away=False, duplicate_key=False
):
    owner = tmp_path / "owner"
    other = tmp_path / "other"
    directory = owner / "feat"
    directory.mkdir(parents=True)
    other.mkdir()
    other_directory = other / "feat"
    if duplicate_key:
        other_directory.mkdir()
    root = PlaceRoot(
        path=owner,
        list=f"echo {shlex.quote(str(directory))}",
        path_of=owner_lookup.replace("{dir}", shlex.quote(str(directory))),
        destroy="true",
    )
    cfg = Config(
        places=PlacesConfig(
            roots=[
                PlaceRoot(
                    path=other,
                    list=f"echo {shlex.quote(str(other_directory))}" if duplicate_key else "true",
                    path_of=f"echo {shlex.quote(str(other_directory))}"
                    if duplicate_key
                    else "false",
                    destroy="true",
                ),
                root,
            ]
        )
    )
    monkeypatch.setattr(target.session, "exists", lambda name: name == "feat")
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1"})
    monkeypatch.setattr(
        ownership,
        "pane_snapshot",
        lambda: [ownership.Pane("feat", "@1", "%1", tmp_path if cd_away else directory)],
    )
    return cfg, directory


@pytest.mark.parametrize("cd_away", [False, True])
def test_unrelated_root_lookup_failure_does_not_veto_cleanup(monkeypatch, tmp_path, cd_away):
    cfg, directory = _workspace(monkeypatch, tmp_path, cd_away=cd_away)
    doomed, why = target.resolve_toss_target(cfg, "feat", unattended=True)
    assert not why
    assert [place.directory for place in doomed.places] == [directory]
    assert not doomed.kept


@pytest.mark.parametrize("cd_away", [False, True])
def test_owning_root_lookup_failure_keeps_directory(monkeypatch, tmp_path, cd_away):
    cfg, directory = _workspace(monkeypatch, tmp_path, owner_lookup="false", cd_away=cd_away)
    doomed, why = target.resolve_toss_target(cfg, "feat", unattended=True)
    assert not why
    assert doomed.places == []
    assert "Directory lookup failed" in doomed.kept[0]
    assert str(directory.parent) in doomed.kept[0]


@pytest.mark.parametrize("failure", ["lookup", "discovery", "protected"])
@pytest.mark.parametrize("as_json", [False, True])
def test_unattended_toss_reports_why_cleanup_was_skipped(
    monkeypatch, tmp_path, capsys, failure, as_json
):
    cfg, directory = _workspace(
        monkeypatch, tmp_path, owner_lookup="false" if failure == "lookup" else "echo {dir}"
    )
    if failure == "discovery":
        cfg.places.roots[0] = PlaceRoot(path=tmp_path / "other", list="false")
    elif failure == "protected":
        cfg.places.roots[1] = PlaceRoot(
            path=directory.parent, list=f"echo {directory}", protected=["feat"], destroy="true"
        )
    monkeypatch.setattr(toss_cli, "load_config", lambda: cfg)
    tossed = []
    monkeypatch.setattr(toss_cli.teardown, "toss", lambda *args: tossed.append(args))
    toss_cli.cmd_toss(argparse.Namespace(key="feat", yes=True, json=as_json, force=False))
    output = capsys.readouterr()
    assert tossed[0][0] == "feat"
    assert tossed[0][1] == []
    reason = {
        "lookup": "Directory lookup failed",
        "discovery": "Directory discovery failed",
        "protected": "protected directory",
    }[failure]
    if as_json:
        result = json.loads(output.out)
        assert result["released"] == []
        assert reason in result["kept"][0]
        assert result["session_closed"]
    else:
        assert reason in output.err


def test_two_roots_cleanup_on_a_private_tmux_server(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")
    snapshot = ownership.pane_snapshot
    exists = target.session.exists
    cfg, directory = _workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(ownership, "pane_snapshot", snapshot)
    monkeypatch.setattr(target.session, "exists", exists)
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: set())
    server = f"lemonaid-cleanup-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", server, *args], capture_output=True, text=True)

    started = tmux(
        "-f", "/dev/null", "new-session", "-d", "-s", "feat", "-c", str(directory), "sleep 30"
    )
    if started.returncode:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")
    try:
        socket = tmux("display-message", "-p", "-t", "feat", "#{socket_path}").stdout.strip()
        monkeypatch.setenv("TMUX", f"{socket},0,0")
        monkeypatch.setattr(toss_cli, "load_config", lambda: cfg)
        released = []
        monkeypatch.setattr(
            toss_cli.teardown, "toss", lambda name, places, partial: released.extend(places)
        )
        toss_cli.cmd_toss(argparse.Namespace(key="feat", yes=True, json=True, force=False))
        assert [place.directory for place in released] == [directory]
    finally:
        tmux("kill-server")


def test_pane_root_limits_same_named_directory_cleanup(monkeypatch, tmp_path):
    cfg, owner_directory = _workspace(monkeypatch, tmp_path, duplicate_key=True)
    doomed, why = target.resolve_toss_target(cfg, "feat", unattended=True)
    assert not why
    assert [place.directory for place in doomed.places] == [owner_directory]


def test_ambiguous_same_named_directories_stay_when_panes_identify_no_root(monkeypatch, tmp_path):
    cfg, _ = _workspace(monkeypatch, tmp_path, duplicate_key=True, cd_away=True)
    doomed, why = target.resolve_toss_target(cfg, "feat", unattended=True)
    assert not why
    assert doomed.places == []
    assert "ambiguous across roots" in doomed.kept[0]
    assert "owner/feat" in doomed.kept[0]
    assert "other/feat" in doomed.kept[0]


def test_nested_pane_root_still_checks_ancestor_place_owner(monkeypatch, tmp_path):
    outer = tmp_path / "outer"
    directory = outer / "feat"
    nested_root = directory / "subproject"
    nested_root.mkdir(parents=True)
    outer_root = PlaceRoot(
        path=outer,
        list=f"echo {shlex.quote(str(directory))}",
        path_of="false",
        destroy="true",
    )
    cfg = Config(places=PlacesConfig(roots=[outer_root, PlaceRoot(path=nested_root)]))
    monkeypatch.setattr(target.session, "exists", lambda name: name == "feat")
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1"})
    monkeypatch.setattr(
        ownership,
        "pane_snapshot",
        lambda: [ownership.Pane("feat", "@1", "%1", nested_root)],
    )

    doomed, why = target.resolve_toss_target(cfg, "feat", unattended=True)

    assert not why
    assert doomed.places == []
    assert "Directory lookup failed" in doomed.kept[0]
    assert str(outer) in doomed.kept[0]
