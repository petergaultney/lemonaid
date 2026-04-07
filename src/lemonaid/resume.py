"""Config-driven resume command building for lemon backends."""

import shlex

from .config import Config

_DEFAULT_RESUME_COMMANDS: dict[str, str] = {
    "claude": "lemonaid claude resume {session_id}",
    "codex": "codex resume {session_id}",
    "openclaw": "openclaw --session {session_key}",
    "opencode": "opencode --session {session_id}",
}


def _backend_name(channel: str) -> str:
    return channel.split(":")[0] if ":" in channel else channel


def _resolve_template(config: Config, channel: str) -> str:
    backend = _backend_name(channel)
    bc = config.backends.get(backend)
    return (bc.resume_command if bc else "") or _DEFAULT_RESUME_COMMANDS.get(backend, "")


def has_resume_command(config: Config, channel: str) -> bool:
    return bool(_resolve_template(config, channel))


def build_resume_command(
    config: Config, channel: str, metadata: dict[str, str]
) -> tuple[str, list[str]] | None:
    """Build (cwd, argv) for resuming a session from its notification.

    Uses the configured resume_command template for the backend, falling
    back to built-in defaults for known backends. The template is formatted
    with all metadata values as keyword arguments, then shlex-split into argv.

    Returns None if there's no cwd in metadata or no resume_command
    configured (or defaulted) for the backend.
    """
    cwd = metadata.get("cwd")
    if not cwd:
        return None

    template = _resolve_template(config, channel)
    if not template:
        return None

    try:
        cmd = template.format_map(metadata)
    except KeyError:
        return None

    return (cwd, shlex.split(cmd))
