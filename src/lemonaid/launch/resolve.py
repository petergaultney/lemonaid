"""Resolve a lemon and its session layout without starting either."""

import dataclasses
import shlex
from collections import abc

from .. import launch_config
from ..config import TmuxSessionConfig
from . import command


@dataclasses.dataclass(frozen=True)
class Resolved:
    lemon: str
    shape: str
    windows: tuple[str, ...]
    lemon_window: int

    @property
    def line(self) -> str:
        return self.windows[self.lemon_window]

    def session_config(self, config: TmuxSessionConfig, name: str) -> TmuxSessionConfig:
        return dataclasses.replace(
            config,
            templates={**config.templates, name: list(self.windows)},
            harness_window=self.lemon_window,
            resume_window=self.lemon_window
            if self.shape in config.shapes
            else config.resume_window,
            launch=launch_config.Settings(),
        )


def resolve(
    config: TmuxSessionConfig,
    harness: str = "default",
    preset: str = "",
    shape: str = "",
    extra: abc.Sequence[str] = (),
) -> Resolved:
    selected = preset or (config.launch.default if harness == "default" else "") or harness
    legacy = config.get_template(selected)
    if (
        (preset or (harness == "default" and config.launch.default))
        and selected not in config.launch.presets
        and legacy is None
    ):
        raise ValueError(f"No lemon preset {selected!r} in config")

    # Old --harness names take precedence over presets with the same name.
    named_preset = bool(preset or (harness == "default" and config.launch.default))
    legacy_selected = legacy is not None and not (
        named_preset and selected in config.launch.presets
    )
    if legacy_selected:
        if not legacy:
            raise ValueError(f"No tmux-session template {selected!r} in config")
        line = legacy[command.template_window(config, legacy)]
    elif selected in config.launch.presets:
        entry = config.launch.presets[selected]
        line = shlex.join([entry.harness, *entry.args])
    elif selected == "default":
        if not (shape or config.launch.shape):
            raise ValueError("No tmux-session template 'default' in config")
        line = ""
    else:
        line = shlex.quote(selected)

    shape_name = shape or config.launch.shape
    if shape_name:
        if shape_name in config.shapes:
            layout = config.shapes[shape_name]
            windows, index = list(layout.windows), layout.lemon_window
        elif template := config.get_template(shape_name):
            windows, index = list(template), command.template_window(config, template)
        else:
            raise ValueError(f"No session shape {shape_name!r} in config")
    else:
        template = legacy if legacy_selected else config.get_template("default")
        windows = list(template) if template else [""]
        index = command.template_window(config, windows)
        shape_name = (
            f"template:{selected if legacy_selected else 'default'}" if template else "shell"
        )

    if extra and not line.strip():
        raise ValueError("Extra lemon arguments need a preset or harness command")

    windows[index] = " ".join(part for part in (line, shlex.join(extra)) if part)
    return Resolved(selected, shape_name, tuple(windows), index)


def entries(config: TmuxSessionConfig) -> list[dict]:
    return [
        {
            "name": name,
            "harness": preset.harness,
            "args": list(preset.args),
            "description": preset.description,
            "tags": list(preset.tags),
            "legacy": False,
        }
        for name, preset in sorted(config.launch.presets.items())
    ] + [
        {
            "name": name,
            "command": windows[command.template_window(config, windows)],
            "description": "Legacy session template",
            "tags": [],
            "legacy": True,
        }
        for name, windows in sorted(config.templates.items())
        if windows
    ]
