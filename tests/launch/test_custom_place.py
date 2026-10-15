import argparse
import json

import pytest

from lemonaid import launch_config
from lemonaid.brief import handoff_launch, store
from lemonaid.config import Config, PlaceRoot, PlacesConfig, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.launch import passthrough
from lemonaid.places import cli
from lemonaid.tmux import session
from tests.test_places_open_launch import _recorder, _wait_for, tmux  # noqa: F401


@pytest.mark.parametrize("use_separator", [False, True])
def test_place_runs_shape_and_custom_lemon_and_attaches_at_shape_slot(
    monkeypatch,
    capsys,
    tmp_path,
    use_separator,
    tmux,  # noqa: F811
):
    executable, out = _recorder(tmp_path)
    editor_marker = tmp_path / "editor"
    config = Config(
        tmux_session=TmuxSessionConfig(
            shapes={"work": launch_config.Shape((f"touch {editor_marker}", ""), 1)},
            launch=launch_config.Settings(
                shape="work", presets={"test": launch_config.Preset(executable, ("--model", "old"))}
            ),
        ),
        places=PlacesConfig(roots=[PlaceRoot(tmp_path, path_of=f"echo {tmp_path}")]),
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Task\n")
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = passthrough.parse_args(
        parser,
        [
            "place",
            "open",
            "new",
            "--root",
            str(tmp_path),
            "--preset",
            "test",
            "--brief",
            str(path),
            "--detach",
            "--json",
            "--no-check",
            *(
                ["--", "--model", "new"]
                if use_separator
                else ["--lemon-arg=--model", "--lemon-arg=new"]
            ),
        ],
    )
    args.func(args)
    assert json.loads(capsys.readouterr().out)["error"] is None
    assert _wait_for(out)
    assert json.loads(out.read_text()) == [
        "--model",
        "old",
        "--model",
        "new",
        f"Task. Your task file is {path.resolve()}; read it all and do the work.",
    ]
    assert editor_marker.exists()
    with db.connect() as conn:
        [pending] = conn.execute("SELECT * FROM pending_briefs").fetchall()
    assert pending["tmux_window"] == "1"


def test_resume_uses_new_default_shape_without_starting_preset(monkeypatch, tmp_path):
    created = []
    monkeypatch.setattr(session, "create_session", lambda **kw: created.append(kw) or True)
    config = TmuxSessionConfig(
        shapes={"work": launch_config.Shape(("editor", ""), 1)},
        launch=launch_config.Settings(
            shape="work",
            default="test",
            presets={"test": launch_config.Preset("claude", ("--model", "custom"))},
        ),
    )
    assert (
        session.spawn_session(
            str(tmp_path), config, resume_argv=["claude", "--resume", "123"], attach=False
        )
        is None
    )
    assert created[0]["windows"] == ["editor", "claude --resume 123"]


def test_handoff_uses_the_same_preset_defaults(monkeypatch):
    config = Config(
        tmux_session=TmuxSessionConfig(
            launch=launch_config.Settings(
                presets={"small": launch_config.Preset("claude", ("--model", "small"))}
            )
        )
    )
    monkeypatch.setattr(handoff_launch, "load_config", lambda: config)
    assert handoff_launch.configured_line("small") == "claude --model small"
