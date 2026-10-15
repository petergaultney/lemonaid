"""Reject configuration drift that cannot be attributed to the running generation."""

import datetime as dt
import hashlib
from collections import abc
from pathlib import Path

from . import environment as launch_env


def snapshot(paths: abc.Iterable[Path], started: str) -> dict[str, str]:
    birth = dt.datetime.strptime(started, "%a %b %d %H:%M:%S %Y").timestamp()
    result = {}
    for path in paths:
        if not path.is_file():
            result[str(path)] = ""
            continue

        if path.stat().st_mtime >= birth + 1:
            raise ValueError(
                f"{path} changed after this harness started; its loaded settings are uncertain"
            )
        result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def paths(
    harness: str, environment: abc.Mapping[str, str], cwd: str, profile: str, argv: list[str]
) -> list[Path]:
    if harness == "codex":
        root = Path(launch_env.homes(environment)["codex"])
        return [root / "config.toml", *([root / f"{profile}.config.toml"] if profile else [])]

    root = Path(launch_env.homes(environment)["claude"])
    settings = [
        root / "settings.json",
        Path(cwd) / ".claude/settings.json",
        Path(cwd) / ".claude/settings.local.json",
    ]
    for index, argument in enumerate(argv):
        flag, equals, value = argument.partition("=")
        if flag != "--settings":
            continue
        if not equals:
            value = argv[index + 1] if index + 1 < len(argv) else ""
        if value and not value.lstrip().startswith("{"):
            settings.append(Path(cwd) / Path(value).expanduser())
    return settings


def unchanged(files: dict[str, str]) -> None:
    for filename, expected in files.items():
        path = Path(filename)
        current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        if current != expected:
            raise ValueError(f"Launch configuration changed: {path}")
