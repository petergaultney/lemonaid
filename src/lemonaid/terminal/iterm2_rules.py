"""An iTerm2 Smart Selection rule, in every profile, that opens vault paths on Cmd-click.

Lemonaid's rule is the one whose notes are `NOTES`; installing replaces it and
leaves the profile's other rules alone. A profile with no rules of its own uses
iTerm2's built-in set, so adding one rule there first copies that set in.
iTerm2 reads profiles at launch: a change shows after it restarts.

Cmd-click on a file that exists normally goes to Semantic History before any
Smart Selection action, so installing also sets `PRIORITIZE`, the advanced
setting that checks Smart Selection actions first.

The match reaches a shell as `\\0` in a Run Command action, and the session's
directory as `\\d`. iTerm2
backslash-escapes it unless the profile uses interpolated strings, and
`SHELL_CHARS` keeps every character that could start another command out of the
match, so a printed path can at worst split into several words.
"""

import plistlib
import shlex
import subprocess
from collections import abc
from pathlib import Path

DOMAIN = "com.googlecode.iterm2"
BUILT_IN_RULES = Path("/Applications/iTerm.app/Contents/Resources/SmartSelectionRules.plist")
NOTES = "Obsidian vault path (managed by lemonaid terminal vault-links)"
SHELL_CHARS = ";&|$`\\\"'()"
PROFILES = "New Bookmarks"
PRIORITIZE = "PrioritizeSmartSelectionActions"

_RULES = "Smart Selection Rules"
_RUN_COMMAND = 2


def rule(regex: str, lemonaid: str) -> dict:
    return {
        "notes": NOTES,
        "precision": "very_high",
        "regex": regex,
        "actions": [
            {
                "title": "Open in Obsidian",
                "action": _RUN_COMMAND,
                "parameter": f"{shlex.quote(lemonaid)} terminal open-vault --cwd \\d -- \\0",
            }
        ],
    }


def built_in_rules(plist: Path) -> list[dict]:
    return plistlib.loads(plist.read_bytes())["Rules"] if plist.exists() else []


def changed(
    profiles: abc.Iterable[dict], new: dict | None, built_in: abc.Sequence[dict]
) -> abc.Iterator[tuple[dict, str]]:
    """Each profile with lemonaid's rule replaced by *new* (or dropped when None), and what changed.

    A profile with no rules of its own is left as is when there is nothing to
    remove, or no built-in set to copy in.
    """
    for profile in profiles:
        own = profile.get(_RULES)
        if own is None and new is None:
            yield profile, "unchanged"
            continue

        if own is None and not built_in:
            yield (
                profile,
                f"skipped: it uses iTerm2's built-in rules, and {BUILT_IN_RULES} is missing",
            )
            continue

        kept = [r for r in (own if own is not None else built_in) if r.get("notes") != NOTES]
        rules = [*kept, *([new] if new else [])]
        if own is not None and rules == own:
            yield profile, "unchanged"
        elif new is None:
            yield {**profile, _RULES: rules}, "removed"
        elif any(r.get("notes") == NOTES for r in own or []):
            yield {**profile, _RULES: rules}, "updated"
        else:
            yield {**profile, _RULES: rules}, "added"


def running() -> bool:
    return subprocess.run(["pgrep", "-xq", "iTerm2"]).returncode == 0


def load(plist: Path | None) -> dict:
    """The preferences in *plist*, or in iTerm2's preferences domain when None."""
    data = (
        plist.read_bytes()
        if plist
        else subprocess.run(
            ["defaults", "export", DOMAIN, "-"], capture_output=True, check=True
        ).stdout
    )
    prefs = plistlib.loads(data)
    if plist is None and prefs.get("LoadPrefsFromCustomFolder"):
        raise RuntimeError(
            "iTerm2 loads its settings from a custom folder; pass that plist with --iterm2-plist"
        )

    return prefs


def save(updates: dict, plist: Path | None) -> None:
    """Merge *updates* into *plist*, or into iTerm2's preferences domain when None.

    `defaults import` merges the keys it is given, so iTerm2's other settings stay.
    """
    if plist is None:
        subprocess.run(
            ["defaults", "import", DOMAIN, "-"], input=plistlib.dumps(updates), check=True
        )
        return

    plist.write_bytes(plistlib.dumps({**plistlib.loads(plist.read_bytes()), **updates}))
