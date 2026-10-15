"""Recover effective Codex fields from native turn context and explicit overrides."""

import json
import tomllib
import typing as ty
from pathlib import Path

from . import arguments


def context(path: str, session: str) -> dict[str, ty.Any]:
    if not path:
        return {}

    found: dict[str, ty.Any] = {}
    identity = ""
    try:
        with Path(path).open() as transcript:
            for line in transcript:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") == "session_meta":
                    identity = entry.get("payload", {}).get("id", "")
                    if entry.get("payload", {}).get("model_provider"):
                        found["model_provider"] = entry["payload"]["model_provider"]
                if entry.get("type") == "turn_context":
                    found.update(entry.get("payload", {}))
    except OSError:
        return {}

    return found if identity == session else {}


def enrich(
    data: dict[str, ty.Any], argv: list[str], session: str, recorded: str
) -> dict[str, ty.Any]:
    found = context(data.get("transcript_path") or data.get("session_path") or recorded, session)
    explicit: dict[str, ty.Any] = {}
    for flag, value in arguments.operating(argv):
        if flag == "--config":
            try:
                explicit.update(tomllib.loads(value))
            except tomllib.TOMLDecodeError:
                continue

    return {**explicit, **found, **data}
