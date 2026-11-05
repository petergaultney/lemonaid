"""Whether Claude Code trusts a directory, read from its global config and never written.

Claude asks whether to trust a directory before it reads a prompt, and has no flag
to skip that. Accepting the prompt records `hasTrustDialogAccepted` for the directory,
and that covers every directory below it.
"""

import json
import os
from pathlib import Path

from ..log import get_logger

_log = get_logger("claude.trust")


def config_file() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home()) / ".claude.json"


def trusted(directory: Path, config: Path) -> bool:
    try:
        projects = json.loads(config.read_text()).get("projects") or {}
    except (OSError, json.JSONDecodeError, AttributeError) as error:
        _log.warning("Could not read Claude's trusted directories from %s: %s", config, error)
        return False

    return any(
        isinstance(entry := projects.get(str(path)), dict)
        and entry.get("hasTrustDialogAccepted") is True
        for path in (directory, *directory.parents)
    )
