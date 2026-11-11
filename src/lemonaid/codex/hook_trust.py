"""Whether Codex runs a hooks.json handler: enabled, and trusted at its current hash.

Codex 0.166 keys each handler's state by `<hooks.json>:<event>:<group>:<handler>` in its
`config.toml` (`[hooks.state]`), and runs it only when it isn't `enabled = false` and its
`trusted_hash` is the hash of the handler as Codex normalizes it: SHA-256 over compact,
key-sorted JSON of the event name and the one handler, with its timeout filled in
(codex-rs/hooks/src/engine/discovery.rs, `hook_hash`). A SessionEnd handler has no
matcher or context limit, and its timeout defaults to one second.
"""

import hashlib
import json
import tomllib
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("codex.hook_trust")

_SESSION_END_DEFAULT_TIMEOUT = 1
_SESSION_END_MAX_TIMEOUT = 3


def _session_end_hash(handler: abc.Mapping[str, ty.Any]) -> str:
    normalized = {
        "type": "command",
        "command": handler["command"],
        "timeout": min(
            max(int(handler.get("timeout") or _SESSION_END_DEFAULT_TIMEOUT), 1),
            _SESSION_END_MAX_TIMEOUT,
        ),
        "async": bool(handler.get("async", False)),
        **({"statusMessage": handler["statusMessage"]} if "statusMessage" in handler else {}),
    }
    identity = json.dumps(
        {"event_name": "session_end", "hooks": [normalized]}, sort_keys=True, separators=(",", ":")
    )
    return f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}"


def _read(path: Path, parse: abc.Callable[[str], dict]) -> dict:
    try:
        return parse(path.read_text())
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as exc:  # JSONDecodeError and TOMLDecodeError are ValueErrors
        _log.warning("cannot read %s: %s", path, exc)
        return {}


def session_end_runs(home: Path, hooks_json: Path, command: str) -> bool:
    """Whether Codex runs the SessionEnd handler in *hooks_json* whose command is *command*."""
    groups = _read(hooks_json, json.loads).get("hooks", {}).get("SessionEnd", [])
    states = _read(home / "config.toml", tomllib.loads).get("hooks", {}).get("state", {})
    return any(
        isinstance(handler, dict)
        and handler.get("command") == command
        and isinstance(state := states.get(f"{hooks_json}:session_end:{group}:{index}"), dict)
        and state.get("enabled") is not False
        and state.get("trusted_hash") == _session_end_hash(handler)
        for group, entry in enumerate(groups)
        if isinstance(entry, dict)
        for index, handler in enumerate(entry.get("hooks", []))
    )
