import pytest

from lemonaid import launch_config
from lemonaid.config import load_config


def test_toml_keeps_shapes_separate_from_named_lemons(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("""
[tmux-session.shapes.work]
windows = ["editor", "", ""]
lemon_window = 1
[launch]
default = "sol"
shape = "work"
[launch.presets.sol]
harness = "codex"
args = ["--no-daemon", "-m", "sol"]
description = "Implementation"
tags = ["code", "medium"]
""")
    config = load_config(path).tmux_session
    assert config.shapes == {"work": launch_config.Shape(("editor", "", ""), 1)}
    assert config.launch.default == "sol"
    assert config.launch.shape == "work"
    assert config.launch.presets["sol"] == launch_config.Preset(
        "codex", ("--no-daemon", "-m", "sol"), "Implementation", ("code", "medium")
    )
    assert not config.templates


@pytest.mark.parametrize(
    "entry",
    [
        {"harness": ""},
        {"harness": "codex", "args": "--flag"},
        {"harness": "codex", "tags": [4]},
        {"args": []},
        "codex",
    ],
)
def test_invalid_presets_fail_with_the_config_location(entry):
    with pytest.raises(ValueError, match=r"launch\.presets\.bad"):
        launch_config.parse({"presets": {"bad": entry}})
