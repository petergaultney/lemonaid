"""Running the configured directory-management commands for a place root.

Everything here treats the configured commands as opaque shell strings and their
output as lines. lemonaid never learns what the tool on the other end is, which
is what keeps worktrees (or whatever else manages directories) out of its model.
"""

import shlex
import subprocess
from pathlib import Path

from ..config import PlaceRoot
from ..log import get_logger

_log = get_logger("places.hooks")

_TIMEOUT_SECONDS = 15  # listing and path lookups are metadata reads, not work


def substitute(template: str, key: str = "", directory: str = "") -> str:
    """Fill in the {key} and {dir} placeholders in a hook command.

    Values are shell-quoted, so a key containing spaces stays one argument and
    can't extend the command it is substituted into.
    """
    return template.replace("{key}", shlex.quote(key)).replace("{dir}", shlex.quote(directory))


def run_lines(
    root: PlaceRoot,
    template: str,
    key: str = "",
    directory: str = "",
    timeout: int = _TIMEOUT_SECONDS,
) -> list[str]:
    """Run a hook and return its non-empty stdout lines.

    Hooks run through a shell, because "emit one path per line" is often most
    naturally a pipeline. They come from the user's own config file, which is the
    same trust level as a shell rc file.

    A hook that fails is a configuration or environment problem rather than
    something the caller can act on, so it logs and yields nothing.
    """
    if not template.strip():
        return []

    command = substitute(template, key, directory)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=root.path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("hook %r in %s failed to run: %s", command, root.path, e)
        return []

    if result.returncode != 0:
        _log.warning(
            "hook %r in %s exited %d: %s",
            command,
            root.path,
            result.returncode,
            result.stderr.strip(),
        )
        return []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_directories(root: PlaceRoot) -> list[Path]:
    """Every directory the root's `list` hook reports, as absolute paths.

    A hook may emit `path\\tlabel`; only the path is used here. Paths are taken
    relative to the root when not absolute, and non-directories are dropped -
    a stale listing shouldn't produce rows that can't be opened.
    """
    directories = []
    for line in run_lines(root, root.list):
        candidate = Path(line.split("\t")[0]).expanduser()
        resolved = candidate if candidate.is_absolute() else root.path / candidate
        if resolved.is_dir():
            directories.append(resolved.resolve())

    return directories


def directory_for_key(root: PlaceRoot, key: str) -> Path | None:
    """Where the root's `path_of` hook says *key* lives, if it exists."""
    for line in run_lines(root, root.path_of, key=key):
        candidate = Path(line).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    return None


def inspect(root: PlaceRoot, directory: Path) -> str:
    """The root's one-line summary of *directory*. Empty means nothing to report.

    The hook decides what is worth saying; lemonaid only displays it.
    """
    return " ".join(run_lines(root, root.inspect, directory=str(directory)))


def create(root: PlaceRoot, key: str, timeout: int) -> Path | None:
    """Acquire a directory for *key* and return it.

    `create` and `path_of` are separate hooks because the tool that creates a
    directory usually reports it by changing its caller's working directory,
    which a subprocess can't observe.
    """
    if not root.create:
        return None

    run_lines(root, root.create, key=key, timeout=timeout)

    return directory_for_key(root, key)


def destroy(root: PlaceRoot, key: str, timeout: int) -> bool:
    """Release the directory for *key*. False if there is no destroy hook."""
    if not root.destroy:
        return False

    run_lines(root, root.destroy, key=key, timeout=timeout)

    return True
