import argparse
import json
import shlex

import pytest

import lemonaid.places.cli
from lemonaid import launch_config
from lemonaid.brief import store
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.launch import cli, handoff, options


def _config():
    return Config(
        tmux_session=TmuxSessionConfig(
            shapes={"work": launch_config.Shape(("editor", "", ""), 1)},
            launch=launch_config.Settings(
                default="sol",
                shape="work",
                presets={
                    "sol": launch_config.Preset(
                        "codex", ("--no-daemon", "-m", "sol"), "Code", ("build",)
                    ),
                },
            ),
        )
    )


def _args(*argv):
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    return parser.parse_args(argv)


def test_list_shows_flags_and_optional_metadata(monkeypatch, capsys):
    monkeypatch.setattr(options, "load_config", _config)
    args = _args("presets", "--json")
    args.func(args)
    [row] = json.loads(capsys.readouterr().out)
    assert row == {
        "name": "sol",
        "harness": "codex",
        "args": ["--no-daemon", "-m", "sol"],
        "description": "Code",
        "tags": ["build"],
        "legacy": False,
    }


def test_show_reports_resolved_flags_and_separate_shape(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(options, "load_config", _config)
    args = _args(
        "presets",
        "show",
        "sol",
        "--lemon-arg=-m",
        "--lemon-arg=custom",
        "--directory",
        str(tmp_path),
        "--json",
    )
    args.func(args)
    actual = json.loads(capsys.readouterr().out)
    assert actual["shape"] == "work"
    assert actual["lemon_window"] == 1
    assert actual["windows"][0] == "editor"
    assert shlex.split(actual["command"])[-4:] == ["-m", "sol", "-m", "custom"]
    assert f'projects={{"{tmp_path}"={{trust_level="trusted"}}}}' in shlex.split(actual["command"])


@pytest.mark.parametrize("kind", ["start", "place"])
def test_dry_run_does_not_query_tmux_acquire_or_attach(monkeypatch, capsys, tmp_path, kind):
    def forbidden(*args, **kwargs):
        pytest.fail("preview attempted to launch or attach")

    monkeypatch.setattr(cli, "load_config", _config)
    monkeypatch.setattr(lemonaid.places.cli, "load_config", _config)
    monkeypatch.setattr(cli.window, "session_dir", forbidden)
    monkeypatch.setattr(handoff, "prepare", forbidden)
    monkeypatch.setattr(lemonaid.places.cli.lifecycle, "open_key", forbidden)
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Task brief\n")
    if kind == "start":
        args = _args("start", "missing:4", "--dry-run", "--brief", str(path), "--json")
    else:
        parser = argparse.ArgumentParser()
        lemonaid.places.cli.setup_parser(parser.add_subparsers())
        args = parser.parse_args(
            ["place", "open", "new", "--dry-run", "--brief", str(path), "--json"]
        )
    args.func(args)
    actual = json.loads(capsys.readouterr().out)
    assert (
        actual["environment"]["LEMONAID_PROMPT"]
        == f"Task. Your task file is {path.resolve()}; read it all and do the work."
    )
    assert actual["shape"] == "work"
    assert "current directory" in actual["note"]
    assert not (tmp_path / "lemonaid.db").exists()


def test_preset_and_harness_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _args("start", "work:4", "--preset", "sol", "--harness", "codex")


def test_empty_legacy_commands_can_be_listed_as_text(monkeypatch, capsys):
    monkeypatch.setattr(
        options,
        "load_config",
        lambda: Config(tmux_session=TmuxSessionConfig(templates={"default": [""]})),
    )
    args = _args("presets")
    args.func(args)
    assert "default:" in capsys.readouterr().out
