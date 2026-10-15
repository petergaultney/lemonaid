"""Install lemonaid's lemon-side hooks in Claude Code and Codex, without disturbing others.

Both read hooks in the same format, Claude from `~/.claude/settings.json` and Codex from
`~/.codex/hooks.json` (`$CODEX_HOME` moves it). Each gets the same three:

- PreToolUse and PostToolUse on every tool: own_change, so a lemon's own edits and pushes
  don't wake its waiters;
- Stop: block ending a turn while the attached brief's waiters aren't armed (stop_check);
  for a Claude lemon, it first starts the push scout when the session can take one;
- SessionStart: start a Claude lemon's push scout, or remind a lemon with an attached brief
  which waiters to arm.

Codex also gets `lemonaid codex tool-used` on PreToolUse and PostToolUse, which clears a
permission notice when its requested tool starts or returns.

Codex trusts a hook by a hash of it (`[hooks.state]` in its `config.toml`), so a hook this
adds or changes runs only once it is trusted again in Codex's `/hooks`.
"""

import os
import shlex
import typing as ty
from pathlib import Path

from ..claude import install_hooks

HARNESSES = ("claude", "codex")


def _ungated_script(harness: str) -> str:
    return "; ".join(
        [
            "d=$(cat)",
            'v() { printf "%s" "$d" | tr ",{" "\\n\\n" | '
            'sed -n "s/^ *\\"$1\\" *: *\\"\\([^\\"]*\\)\\".*/\\1/p" | sort -u; }',
            "s=$(v session_id | head -n1)",
            '[ -n "$s" ] || exit 0',
            f'printf "%s" "$d" | exec lemonaid hooks own-change --harness {harness}',
        ]
    )


def _own_change_script(harness: str) -> str:
    return _ungated_script(harness).replace(
        '[ -n "$s" ] || exit 0',
        "; ".join(
            [
                f'w="${{LEMONAID_STATE_DIR:-$HOME/.local/state/lemonaid}}/own-edits/{harness}-$s"',
                '[ -n "$s" ] && [ -d "$w" ] || exit 0',
                'set -- "$w"/*.doc',
                '[ -e "$w/brief" ] || [ -e "$1" ] || case "$d" in *git*push*) ;; *) exit 0 ;; esac',
            ]
        ),
    )


def own_change_command(harness: str) -> str:
    """Skip unbriefed sessions without doc watches or pushes in the shell."""
    return f"sh -c {shlex.quote(_own_change_script(harness))}"


def previous_own_change_command(harness: str) -> str:
    """The pre-unified command gated on a running waiter's registrations."""
    script = _ungated_script(harness).replace(
        '[ -n "$s" ] || exit 0',
        "; ".join(
            [
                f'w="${{LEMONAID_STATE_DIR:-$HOME/.local/state/lemonaid}}/own-edits/{harness}-$s"',
                '[ -n "$s" ] && [ -d "$w" ] || exit 0',
                'set -- "$w"/*.doc',
                '[ -e "$1" ] || case "$d" in *git*push*) ;; *) exit 0 ;; esac',
            ]
        ),
    )
    return f"sh -c {shlex.quote(script)}"


_CODEX_TOOL_USED_COMMAND = "lemonaid codex tool-used"


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
        ("UserPromptSubmit", f"lemonaid hooks turn-start --harness {harness}"),
        ("PreToolUse", own_change_command(harness)),
        ("PostToolUse", own_change_command(harness)),
        ("Stop", stop_command(harness)),
        ("SessionStart", session_start_command(harness)),
        *(
            [
                ("PreToolUse", _CODEX_TOOL_USED_COMMAND),
                ("PostToolUse", _CODEX_TOOL_USED_COMMAND),
            ]
            if harness == "codex"
            else []
        ),
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
    migrated = []
    for previous, event in (
        (command, event)
        for command in (
            previous_own_change_command(harness),
            f"sh -c {shlex.quote(_ungated_script(harness))}",
        )
        for event in ("PreToolUse", "PostToolUse")
    ):
        if (not events or event in events) and install_hooks.has_command(
            install_hooks.load(path).get("hooks", {}).get(event, []), previous
        ):
            migrated.append(
                f"would replace the previous own-change {event} hook in {path}"
                if dry_run
                else install_hooks.uninstall(event, previous, path)
            )
    return [
        *migrated,
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
