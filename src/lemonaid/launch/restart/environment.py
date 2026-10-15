"""Freeze native defaults and unset overrides independently of the caller."""

import os
from collections import abc
from pathlib import Path

KEYS = (
    "HOME",
    "PATH",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
)


def homes(snapshot: abc.Mapping[str, str | None]) -> dict[str, str]:
    home = Path(snapshot.get("HOME") or Path.home())
    return {
        harness: str(Path(snapshot.get(key) or home / default).expanduser().resolve())
        for harness, key, default in (
            ("claude", "CLAUDE_CONFIG_DIR", ".claude"),
            ("codex", "CODEX_HOME", ".codex"),
        )
    }


def capture(harness: str, source: abc.Mapping[str, str]) -> dict[str, str | None]:
    snapshot = {key: source.get(key) for key in KEYS}
    if harness == "codex" and snapshot["PATH"] is not None:
        root = Path(homes(snapshot)["codex"]) / "tmp/arg0"
        # This directory is generated afresh by Codex; replaying it uses a stale nonce.
        entries = [
            part
            for part in snapshot["PATH"].split(os.pathsep)
            if not (Path(part).parent == root and Path(part).name.startswith("codex-arg0"))
        ]
        snapshot["PATH"] = os.pathsep.join(dict.fromkeys(entries))
    return snapshot


def validate(settings: dict) -> None:
    if not set(KEYS) <= settings.get("environment", {}).keys() or not settings.get("native_homes"):
        raise ValueError(
            "Native environment binding is incomplete; obtain a fresh native hook observation"
        )


def apply(snapshot: abc.Mapping[str, str | None]) -> dict[str, str]:
    result = dict(os.environ)
    for key, value in snapshot.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def prefix(snapshot: abc.Mapping[str, str | None]) -> list[str]:
    return [
        "/usr/bin/env",
        *(part for key, value in snapshot.items() if value is None for part in ("-u", key)),
        *(f"{key}={value}" for key, value in snapshot.items() if value is not None),
    ]


def values(snapshot: abc.Mapping[str, str | None]) -> dict[str, str]:
    """tmux accepts assignments; the exec prefix clears absent values after shell startup."""
    return {key: value for key, value in snapshot.items() if value is not None}
