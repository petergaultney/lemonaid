import dataclasses
import shlex

import pytest

from lemonaid import launch_config
from lemonaid.config import TmuxSessionConfig
from lemonaid.launch import resolve


def _config():
    return TmuxSessionConfig(
        templates={"default": ["editor", "claude --old", ""], "old": ["", "codex --no-daemon"]},
        resume_window=1,
        shapes={
            "solo": launch_config.Shape(("",)),
            "work": launch_config.Shape(("editor", "", "shell"), 1),
        },
        launch=launch_config.Settings(
            default="sol",
            shape="work",
            presets={
                "sol": launch_config.Preset("codex", ("--no-daemon", "-m", "sol")),
                "small": launch_config.Preset("claude", ("--model", "small")),
            },
        ),
    )


@pytest.mark.parametrize("preset", ["sol", "small"])
@pytest.mark.parametrize("shape,index,count", [("work", 1, 3), ("solo", 0, 1)])
def test_any_preset_fits_any_shape(preset, shape, index, count):
    config = _config()
    actual = resolve.resolve(
        config, preset=preset, shape=shape, extra=["--model", "custom", "-c", 'effort="high"']
    )
    assert actual.lemon_window == index
    assert len(actual.windows) == count
    assert shlex.split(actual.line) == [
        config.launch.presets[preset].harness,
        *config.launch.presets[preset].args,
        "--model",
        "custom",
        "-c",
        'effort="high"',
    ]
    if shape == "work":
        assert actual.windows[0] == "editor"
        assert actual.windows[2] == "shell"
    assert config.shapes[shape].windows[index] == ""


def test_defaults_select_shape_and_lemon_independently():
    actual = resolve.resolve(_config())
    assert (actual.lemon, actual.shape, actual.lemon_window) == ("sol", "work", 1)


def test_executable_needs_no_preset():
    actual = resolve.resolve(_config(), harness="/path/custom", shape="solo", extra=["--flag"])
    assert actual.windows == ("/path/custom --flag",)


def test_legacy_config_is_unchanged_and_compound_flags_append():
    config = TmuxSessionConfig(
        templates={"default": ["editor", "setup && claude --old", ""]}, resume_window=1
    )
    assert resolve.resolve(config).windows == tuple(config.templates["default"])
    actual = resolve.resolve(config, extra=["--model", "new"])
    assert actual.line == "setup && claude --old --model new"


def test_legacy_lemon_can_use_an_independent_shape():
    actual = resolve.resolve(_config(), harness="old", shape="solo", extra=["--flag"])
    assert actual.windows == ("codex --no-daemon --flag",)


def test_legacy_shape_can_be_used_with_a_new_preset():
    config = dataclasses.replace(_config(), launch=dataclasses.replace(_config().launch, shape=""))
    actual = resolve.resolve(config, preset="small")
    assert actual.windows == ("editor", "claude --model small", "")
    assert actual.shape == "template:default"


def test_builtin_shell_shape_allows_config_free_harness():
    actual = resolve.resolve(TmuxSessionConfig(), harness="codex", extra=["--no-daemon"])
    assert actual.windows == ("codex --no-daemon",)
    assert actual.shape == "shell"


@pytest.mark.parametrize(
    "kwargs,match",
    [({"preset": "missing"}, "No lemon preset"), ({"shape": "missing"}, "No session shape")],
)
def test_unknown_names_are_rejected(kwargs, match):
    with pytest.raises(ValueError, match=match):
        resolve.resolve(_config(), **kwargs)


def test_legacy_name_wins_for_harness_and_explicit_preset_disambiguates():
    config = _config()
    config.templates["sol"] = ["editor", "legacy"]
    assert resolve.resolve(config, harness="sol").line == "legacy"
    assert resolve.resolve(config, preset="sol").line == "codex --no-daemon -m sol"


def test_bad_default_preset_is_not_an_executable():
    config = TmuxSessionConfig(launch=launch_config.Settings(default="typo"))
    with pytest.raises(ValueError, match="No lemon preset"):
        resolve.resolve(config)


def test_arguments_without_a_lemon_are_refused():
    config = TmuxSessionConfig(shapes={"solo": launch_config.Shape(("",))})
    with pytest.raises(ValueError, match="need a preset or harness"):
        resolve.resolve(config, shape="solo", extra=["--model", "small"])


def test_explicit_preset_ignores_colliding_legacy_layout():
    config = TmuxSessionConfig(
        templates={"default": ["editor", "", "shell"], "small": ["legacy"]},
        harness_window=1,
        launch=launch_config.Settings(
            presets={"small": launch_config.Preset("claude", ("--model", "small"))}
        ),
    )
    selected = resolve.resolve(config, preset="small")
    assert selected.windows == ("editor", "claude --model small", "shell")
    assert selected.shape == "template:default"
    assert selected.lemon_window == 1
    assert resolve.resolve(config, harness="small").windows == ("legacy",)


def test_configured_preset_default_ignores_a_colliding_legacy_layout():
    config = TmuxSessionConfig(
        templates={"default": ["editor", "", "shell"], "small": ["legacy"]},
        harness_window=1,
        launch=launch_config.Settings(
            default="small", presets={"small": launch_config.Preset("claude", ("--model", "small"))}
        ),
    )
    assert resolve.resolve(config).windows == ("editor", "claude --model small", "shell")
    assert resolve.resolve(config, harness="small").windows == ("legacy",)
