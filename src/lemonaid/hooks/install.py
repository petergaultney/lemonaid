"""Install lemonaid's lemon-side hooks in Claude Code and Codex, without disturbing others.

Both read hooks in the same format, Claude from `~/.claude/settings.json` and Codex from
`~/.codex/hooks.json` (`$CODEX_HOME` moves it). Each gets the same three:

- PreToolUse and PostToolUse on every tool: own_change, so a lemon's own edits and pushes
  don't wake its waiters;
- Stop: block ending a turn while the attached brief's waiters aren't armed (waiter_check);
- SessionStart: remind a lemon with an attached brief which waiters to arm.

Codex trusts a hook by a hash of it (`[hooks.state]` in its `config.toml`), so a hook this
adds or changes runs only once it is trusted again in Codex's `/hooks`.
"""

import os
import shlex
import typing as ty
from pathlib import Path

from ..claude import install_hooks

HARNESSES = ("claude", "codex")


def _own_change_script(harness: str) -> str:
    return "; ".join(
        [
            "d=$(cat)",
            'v() { printf "%s" "$d" | tr ",{" "\\n\\n" | '
            'sed -n "s/^ *\\"$1\\" *: *\\"\\([^\\"]*\\)\\".*/\\1/p" | sort -u; }',
            "s=$(v session_id | head -n1)",
            f'w="${{LEMONAID_STATE_DIR:-$HOME/.local/state/lemonaid}}/own-edits/{harness}-$s"',
            '[ -n "$s" ] && [ -d "$w" ] || exit 0',
            'set -- "$w"/*.doc',
            '[ -e "$1" ] || case "$d" in *git*push*) ;; *) exit 0 ;; esac',
            f'printf "%s" "$d" | exec lemonaid hooks own-change --harness {harness}',
        ]
    )


def own_change_command(harness: str) -> str:
    """Runs before and after every tool call, so it starts Python only in a session whose
    waiters registered its directory (own_edits.register, own_pushes.register): every call
    when a doc is watched, and otherwise only a call that mentions a push."""
    return f"sh -c {shlex.quote(_own_change_script(harness))}"


def stop_command(harness: str) -> str:
    return (
        install_hooks.WAITER_CHECK_COMMAND
        if harness == "claude"
        else f"lemonaid hooks stop --harness {harness}"
    )


def session_start_command(harness: str) -> str:
    return f"lemonaid hooks session-start --harness {harness}"


def hooks(harness: str) -> list[tuple[str, str]]:
    """(event, command) for every hook lemonaid installs in `harness`."""
    return [
        ("PreToolUse", own_change_command(harness)),
        ("PostToolUse", own_change_command(harness)),
        ("Stop", stop_command(harness)),
        ("SessionStart", session_start_command(harness)),
    ]


def settings_path(harness: str) -> Path:
    if harness == "claude":
        return install_hooks.settings_path()

    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "hooks.json"


_LEGACY_OWN_EDIT_COMMAND = "sh -c " + shlex.quote(
    "; ".join(
        [
            "d=$(cat)",
            'v() { printf "%s" "$d" | tr ",{" "\\n\\n" | '
            'sed -n "s/^ *\\"$1\\" *: *\\"\\([^\\"]*\\)\\".*/\\1/p" | sort -u; }',
            "s=$(v session_id)",
            '[ -n "$s" ] && [ -d "${TMPDIR:-/tmp}/watch-doc/own/claude-$s" ] || exit 0',
            'case "$(v file_path)" in *.md*) ;; *) exit 0 ;; esac',
            'printf "%s" "$d" | exec lemonaid claude own-edit',
        ]
    )
)
# What `lemonaid claude hooks --own-edits` installed before 0.110: Edit and Write only.


def _without_legacy(path: Path, dry_run: bool) -> ty.Iterator[str]:
    for event in ("PreToolUse", "PostToolUse"):
        settings = install_hooks.load(path)
        if not install_hooks.has_command(
            settings.get("hooks", {}).get(event, []), _LEGACY_OWN_EDIT_COMMAND
        ):
            continue

        yield (
            f"would remove the Edit/Write-only own-edit {event} hook from {path}"
            if dry_run
            else install_hooks.uninstall(event, _LEGACY_OWN_EDIT_COMMAND, path)
        )


def install(
    harness: str,
    path: Path | None = None,
    dry_run: bool = False,
    events: ty.Collection[str] = (),
) -> list[str]:
    """Add lemonaid's hooks (only those for `events`, when given); the lines to print."""
    path = path or settings_path(harness)
    return [
        *(_without_legacy(path, dry_run) if harness == "claude" else []),
        *(
            install_hooks.install(event, command, path, dry_run)
            for event, command in hooks(harness)
            if not events or event in events
        ),
    ]


def uninstall(harness: str, path: Path | None = None, events: ty.Collection[str] = ()) -> list[str]:
    path = path or settings_path(harness)
    return [
        install_hooks.uninstall(event, command, path)
        for event, command in hooks(harness)
        if not events or event in events
    ]
