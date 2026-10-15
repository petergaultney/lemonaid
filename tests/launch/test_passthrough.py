import argparse
import json
import os
import shlex
import subprocess
import sys

import pytest

from lemonaid.launch import passthrough


@pytest.mark.parametrize(
    "route",
    [
        ["place", "open", "new", "--preset", "sol", "--dry-run", "--json"],
        ["lemon", "start", "work:4", "--preset", "sol", "--dry-run", "--json"],
        ["lemon", "presets", "show", "sol", "--json"],
    ],
)
@pytest.mark.parametrize("prefix", [[], ["--lemon-arg=before"]])
def test_public_cli_passes_every_token_after_separator_to_the_lemon(tmp_path, route, prefix):
    config = tmp_path / "config.toml"
    config.write_text("""
[launch.presets.sol]
harness = "echo"
args = ["--model", "default"]
""")
    extra = ["--model", "custom", "two words", 'effort="high"', "--json", "--help", "--", ""]
    result = subprocess.run(
        [sys.executable, "-m", "lemonaid", *route, *prefix, "--", *extra],
        env={**os.environ, "LEMONAID_CONFIG": str(config)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert shlex.split(output["command"]) == [
        "echo",
        "--model",
        "default",
        *(["before"] if prefix else []),
        *extra,
    ]
    assert output["lemon"] == "sol"


@pytest.mark.parametrize(
    "route",
    [
        ["place", "open", "new"],
        ["lemon", "start", "work:4"],
        ["lemon", "presets", "show", "sol"],
    ],
)
def test_unknown_flags_before_separator_are_not_forwarded(route):
    result = subprocess.run(
        [sys.executable, "-m", "lemonaid", *route, "--unknown-harness-flag"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --unknown-harness-flag" in result.stderr


def test_other_commands_keep_argparses_separator_behavior():
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers().add_parser("other")
    command.add_argument("value")
    args = passthrough.parse_args(parser, ["other", "--", "--json"])
    assert args.value == "--json"
    assert not hasattr(args, "lemon_args")
