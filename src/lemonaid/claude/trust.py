"""Whether Claude Code trusts a directory, as its global config records.

Claude asks whether to trust a directory before it reads a prompt, and has no flag
to skip that. Accepting the prompt records `hasTrustDialogAccepted` under a path.
Claude looks that up by the git repository root (or a worktree's own path), and
lemonaid can't find either without git, so only an entry for the directory itself
counts: a trusted parent doesn't cover a repository cloned under it.
"""

import contextlib
import json
import os
import time
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("claude.trust")

_STALE_SECONDS = 10  # proper-lockfile's default: a lock not refreshed this long is abandoned
_WAIT_SECONDS = 5


def config_file() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home()) / ".claude.json"


def trusted(directory: Path, config: Path) -> bool:
    try:
        projects = json.loads(config.read_text()).get("projects") or {}
    except (OSError, json.JSONDecodeError, AttributeError) as error:
        _log.warning("Could not read Claude's trusted directories from %s: %s", config, error)
        return False

    entry = projects.get(str(directory))
    return isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True


@contextlib.contextmanager
def _locked(config: Path) -> abc.Iterator[None]:
    """Hold the lock Claude takes around its own config saves: the `<config>.lock`
    directory of the `proper-lockfile` package, which Claude's holders refresh while
    they write. Claude re-reads the file inside that lock, so it keeps what we add."""
    lock = config.with_name(config.name + ".lock")
    deadline = time.monotonic() + _WAIT_SECONDS
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            with contextlib.suppress(FileNotFoundError):
                if time.time() - lock.stat().st_mtime > _STALE_SECONDS:
                    lock.rmdir()
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{lock} stayed held; Claude may be saving its config") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.rmdir()


def grant(directory: Path, config: Path) -> None:
    """Record that Claude trusts *directory*, as accepting its prompt would.

    The file is replaced whole in one rename, so a Claude reading it outside the
    lock never sees half of it.
    """
    with _locked(config):
        target = config.resolve()
        data = json.loads(target.read_text())
        projects = data.setdefault("projects", {})
        projects.setdefault(str(directory), {})["hasTrustDialogAccepted"] = True
        staged = target.with_name(f".{target.name}.lemonaid-{os.getpid()}")
        staged.write_text(json.dumps(data, indent=2))
        staged.chmod(target.stat().st_mode & 0o777)
        os.replace(staged, target)
    _log.info("Recorded Claude's trust in %s in %s", directory, target)
