import argparse
import json
import time

import pytest

from lemonaid import launch_config
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.launch import cli, passthrough

from .test_cli import tmux  # noqa: F401


@pytest.mark.parametrize("use_separator", [False, True])
def test_start_passes_extra_arguments_after_preset_defaults(
    monkeypatch,
    tmp_path,
    tmux,  # noqa: F811
    capsys,
    use_separator,
):
    recorded = tmp_path / "args.json"
    script = tmp_path / "harness"
    script.write_text(
        f"#!/usr/bin/env python3\nimport json, sys\nopen({str(recorded)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    script.chmod(0o755)
    config = Config(
        tmux_session=TmuxSessionConfig(
            shapes={"work": launch_config.Shape(("SHOULD-NOT-RUN", ""), 1)},
            launch=launch_config.Settings(
                shape="work",
                presets={"test": launch_config.Preset(str(script), ("--model", "old"))},
            ),
        )
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    parser = argparse.ArgumentParser()
    lemon = parser.add_subparsers().add_parser("lemon")
    cli.add_parser(lemon.add_subparsers())
    args = passthrough.parse_args(
        parser,
        [
            "lemon",
            "start",
            "work:4",
            "--preset",
            "test",
            "--prompt",
            "go",
            "--json",
            "--no-check",
            *(
                ["--", "--model", "new", "space value"]
                if use_separator
                else ["--lemon-arg=--model", "--lemon-arg=new", "--lemon-arg=space value"]
            ),
        ],
    )
    args.func(args)
    assert json.loads(capsys.readouterr().out)["error"] is None
    for _ in range(100):
        if recorded.exists():
            break
        time.sleep(0.05)
    assert json.loads(recorded.read_text()) == [
        "--model",
        "old",
        "--model",
        "new",
        "space value",
        "go",
    ]
    assert tmux("list-windows", "-t", "work", "-F", "#{window_index}").splitlines() == ["0", "4"]
