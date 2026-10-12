"""`lemonaid terminal`: terminal rules that open a vault path, as printed, in Obsidian."""

import argparse
import difflib
import os
import plistlib
import shutil
import subprocess
import sys
from collections import abc
from pathlib import Path

from .. import obsidian
from ..config import load_config
from . import iterm2_rules, pattern, vault_files, wezterm_rules


def _wezterm_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "wezterm"


def _wezterm(args: argparse.Namespace, roots: abc.Sequence[Path], lemonaid: str) -> None:
    config_dir: Path = args.wezterm_dir
    module = wezterm_rules.module_path(config_dir)
    folders = vault_files.spaced_folders(roots)
    text = (
        ""
        if args.remove
        else wezterm_rules.module_text(
            pattern.vault_path_regex(roots, spaced_folders=folders), lemonaid
        )
    )
    if args.print:
        print(text, end="")
        return

    if not config_dir.is_dir():
        sys.exit(f"No WezTerm config directory at {config_dir}; pass --wezterm-dir")

    before = module.read_text() if module.exists() else ""
    if before == text:
        print(f"{module}: unchanged")
    elif args.dry_run:
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            text.splitlines(keepends=True),
            str(module),
            str(module),
        )
        sys.stdout.writelines(diff)
    elif args.remove:
        module.unlink()
        print(f"{module}: removed")
    else:
        module.write_text(text)
        print(f"{module}: written")

    if not args.remove and not wezterm_rules.requires_module(config_dir):
        print(
            f"\nAdd these lines to {config_dir / 'wezterm.lua'}, after `config` is built"
            f" and any hyperlink_rules are set:\n\n{wezterm_rules.REQUIRE}"
        )


def _iterm2(args: argparse.Namespace, roots: abc.Sequence[Path], lemonaid: str) -> None:
    folders = vault_files.spaced_folders(roots, iterm2_rules.SHELL_CHARS)
    new = (
        None
        if args.remove
        else iterm2_rules.rule(
            pattern.vault_path_regex(roots, iterm2_rules.SHELL_CHARS, folders), lemonaid
        )
    )
    if args.print:
        print(plistlib.dumps(new or {}).decode(), end="")
        return

    try:
        prefs = iterm2_rules.load(args.iterm2_plist)
    except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError) as error:
        sys.exit(f"Could not read iTerm2's preferences: {error}")

    built_in = iterm2_rules.built_in_rules(iterm2_rules.BUILT_IN_RULES)
    results = list(iterm2_rules.changed(prefs.get(iterm2_rules.PROFILES, []), new, built_in))
    changes = {"added", "updated", "removed"}
    would = "would be " if args.dry_run else ""
    for profile, verb in results:
        print(f"{profile.get('Name', '?')}: {would if verb in changes else ''}{verb}")

    prioritize = new is not None and not prefs.get(iterm2_rules.PRIORITIZE)
    if prioritize:
        print(
            f"{iterm2_rules.PRIORITIZE} (Settings > Advanced: smart selection actions before"
            f" existing files on cmd-click): {would}turned on"
        )

    updates = {
        **(
            {iterm2_rules.PROFILES: [profile for profile, _ in results]}
            if any(verb in changes for _, verb in results)
            else {}
        ),
        **({iterm2_rules.PRIORITIZE: True} if prioritize else {}),
    }
    if args.dry_run or not updates:
        return

    iterm2_rules.save(updates, args.iterm2_plist)
    print("Restart iTerm2 to load the change.")
    if args.iterm2_plist is None and iterm2_rules.running():
        print(
            "iTerm2 is running: if it saves its profiles before it restarts (for example after"
            " an edit in Settings), it writes back the old rules. Check with --dry-run after"
            " restarting."
        )


def cmd_vault_links(args: argparse.Namespace) -> None:
    roots = load_config().brief.vaults
    if not roots and not args.remove:
        sys.exit("No vault roots: set `vaults` under [brief] in lemonaid's config")

    lemonaid = shutil.which("lemonaid") or "lemonaid"
    install = _wezterm if args.terminal == "wezterm" else _iterm2
    install(args, roots, lemonaid)


def _open(target: str) -> None:
    subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", target], check=True)


def cmd_open_vault(args: argparse.Namespace) -> None:
    vaults = load_config().brief.vaults
    given = Path(" ".join(args.path).strip())
    if not given.is_absolute() and given.parts[:1] != ("~",) and (args.cwd / given).is_file():
        _open(str(args.cwd / given))
        return

    path = vault_files.resolve(given, vaults)
    if path is None:
        sys.exit(f"{given} does not exist here or under any vault root")

    if not path.is_file():
        sys.exit(f"{path} does not exist")

    url = obsidian.vault_link(path, vaults)
    if url is None:
        sys.exit(f"{given} is not a .md file under a `[brief] vaults` root")

    _open(url)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("terminal", help="Terminal rules for text lemons print")
    terminal = parser.add_subparsers(dest="terminal_command", required=True)

    links = terminal.add_parser(
        "vault-links",
        help="Install a terminal rule that opens vault paths in Obsidian",
        description="Make a printed `.md` path under a `[brief] vaults` root open in Obsidian"
        " when clicked. Installing again replaces only lemonaid's rule.",
    )
    links.add_argument("terminal", choices=["wezterm", "iterm2"])
    action = links.add_mutually_exclusive_group()
    action.add_argument("--print", action="store_true", help="Print the rule; change nothing")
    action.add_argument("--dry-run", action="store_true", help="Show what would change")
    links.add_argument("--remove", action="store_true", help="Remove lemonaid's rule")
    links.add_argument(
        "--wezterm-dir", type=Path, default=_wezterm_dir(), help="WezTerm's config directory"
    )
    links.add_argument(
        "--iterm2-plist",
        type=Path,
        help="An iTerm2 preferences plist to edit instead of iTerm2's live preferences",
    )
    links.set_defaults(func=cmd_vault_links)

    open_vault = terminal.add_parser(
        "open-vault", help="Open a `.md` path under a vault root in Obsidian"
    )
    open_vault.add_argument(
        "--cwd", type=Path, default=Path.cwd(), help="Where a relative path is first looked for"
    )
    open_vault.add_argument("path", nargs="+", help="The path; several words are joined by spaces")
    open_vault.set_defaults(func=cmd_open_vault)
