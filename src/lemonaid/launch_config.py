"""Independent session shapes and named lemon commands."""

import typing as ty
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Shape:
    windows: tuple[str, ...]
    lemon_window: int = 0


@dataclass(frozen=True)
class Preset:
    harness: str
    args: tuple[str, ...] = ()
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Settings:
    default: str = ""
    shape: str = ""
    presets: dict[str, Preset] = field(default_factory=dict)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")

    return tuple(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")

    return value


def _table(value: object, label: str) -> dict[str, ty.Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a table")

    return value


def parse_shapes(raw: object) -> dict[str, Shape]:
    shapes = {}
    for name, entry in _table(raw, "[tmux-session.shapes]").items():
        label = f"[tmux-session.shapes.{name}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be a table")
        windows = _strings(entry.get("windows"), f"{label} windows")
        index = entry.get("lemon_window", 0)
        if type(index) is not int or not 0 <= index < len(windows):
            raise ValueError(f"{label} lemon_window must index a nonempty windows array")
        shapes[name] = Shape(windows, index)

    return shapes


def parse(raw: object) -> Settings:
    raw = _table(raw, "[launch]")
    presets = {}
    for name, entry in _table(raw.get("presets", {}), "[launch.presets]").items():
        label = f"[launch.presets.{name}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be a table")
        harness = _string(entry.get("harness"), f"{label} harness")
        if not harness.strip():
            raise ValueError(f"{label} harness must name an executable")
        presets[name] = Preset(
            harness,
            _strings(entry.get("args", []), f"{label} args"),
            _string(entry.get("description", ""), f"{label} description"),
            _strings(entry.get("tags", []), f"{label} tags"),
        )

    return Settings(
        _string(raw.get("default", ""), "[launch] default"),
        _string(raw.get("shape", ""), "[launch] shape"),
        presets,
    )
