"""Lemonaid's OpenClaw plugin: installing it into a gateway, and noticing when it is stale.

The plugin's files (`gateway_plugin/`) ship in the wheel. `install` copies them to
`<lemonaid state dir>/openclaw-plugin/`, a path that survives reinstalling lemonaid, with a
`lemonaid.json` naming the Python that runs `lemonaid openclaw hook` and the `LEMONAID_*`
variables set where it ran, since the gateway's environment has neither. OpenClaw loads the copy
by a link, so a reinstall that changed it needs `openclaw plugins reload lemonaid`.

Each hook call carries the version that installed the copy; one that differs from lemonaid's
own is recorded in `stale`, which `status` reports.
"""

import filecmp
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from collections import abc
from pathlib import Path

from ..log import get_logger
from ..watch import own_edits

_log = get_logger("openclaw.plugin")

ID = "lemonaid"
_SOURCE = Path(__file__).parent / "gateway_plugin"
_SETTINGS = "lemonaid.json"
_LINKED = "linked"  # OpenClaw has the link and the grant, so a reinstall only reloads
_RELOAD = "reload"  # the copy changed and OpenClaw hasn't loaded it yet
_ACTIVE = "active"  # OpenClaw has loaded the plugin once
_STALE = "stale"

Run = abc.Callable[[list[str]], None]


def root() -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "openclaw-plugin"


def version() -> str:
    try:
        return importlib.metadata.version("lemonaid-inbox")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def installed() -> bool:
    """Whether the plugin reports this machine's OpenClaw turns, so nothing else need."""
    return (root() / _ACTIVE).is_file()


def note_version(reported: str) -> None:
    stale = root() / _STALE
    if reported == version():
        stale.unlink(missing_ok=True)
        return

    if not stale.is_file() or stale.read_text().strip() != reported:
        _log.warning(
            "OpenClaw's lemonaid plugin is from %s, lemonaid is %s: run "
            "`lemonaid openclaw plugin install`",
            reported,
            version(),
        )
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text(reported + "\n")


def _settings() -> dict:
    return {
        "python": sys.executable,
        "version": version(),
        "ownEdits": str(own_edits.root()),
        "env": {k: v for k, v in sorted(os.environ.items()) if k.startswith("LEMONAID_")},
    }


def _copy() -> bool:
    """Whether the copy changed."""
    target = root()
    target.mkdir(parents=True, exist_ok=True)
    changed = False
    for source in sorted(_SOURCE.iterdir()):
        copy = target / source.name
        if not (copy.is_file() and filecmp.cmp(source, copy, shallow=False)):
            shutil.copyfile(source, copy)
            changed = True
    settings = json.dumps(_settings(), indent=2) + "\n"
    path = target / _SETTINGS
    if not path.is_file() or path.read_text() != settings:
        path.write_text(settings)
        changed = True
    return changed


def _openclaw(cli: str) -> Run:
    def run(arguments: list[str]) -> None:
        print("$", cli, *arguments)
        subprocess.run([cli, *arguments], check=True)

    return run


def install(cli: str, run: Run | None = None) -> None:
    """Raises CalledProcessError when an `openclaw` command fails; running this again resumes,
    retrying a reload that failed."""
    run = run or _openclaw(cli)
    target = root()
    if _copy() or not (target / _ACTIVE).is_file():
        (target / _RELOAD).write_text("")
    if not (target / _LINKED).is_file():
        run(["plugins", "install", "--link", "--force", str(target)])  # confirms a local source
        run(["config", "set", f"plugins.entries.{ID}.hooks.allowConversationAccess", "true"])
        (target / _LINKED).write_text("")
    if (target / _RELOAD).is_file():
        run(["plugins", "reload", ID])
        (target / _ACTIVE).write_text("")
        (target / _RELOAD).unlink()
    (target / _STALE).unlink(missing_ok=True)


def uninstall(cli: str, run: Run | None = None) -> None:
    run = run or _openclaw(cli)
    if (root() / _LINKED).is_file():
        run(["plugins", "uninstall", ID, "--force"])
    shutil.rmtree(root(), ignore_errors=True)


def status() -> str:
    if (root() / _RELOAD).is_file():
        return "not loaded: OpenClaw hasn't loaded the plugin's latest copy; run `lemonaid openclaw plugin install`"

    if not installed():
        return "not installed: run `lemonaid openclaw plugin install` on the gateway's machine"

    stale = root() / _STALE
    if stale.is_file():
        return (
            f"stale: the gateway runs the plugin from {stale.read_text().strip()}, lemonaid is "
            f"{version()}; run `lemonaid openclaw plugin install`"
        )

    return f"installed from {version()} at {root()}"
