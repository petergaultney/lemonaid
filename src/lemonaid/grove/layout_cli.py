"""`lemonaid grove propose|apply`: a block layout a lemon tries out in a file of its own, then applies."""

__lazy_modules__ = ["lemonaid.grove.source"]

import argparse
import json
import sys
from pathlib import Path

from ..config import load_config
from .layout import arrange, edit, landmarks, proposal, state
from .source import live


def _fail(args: argparse.Namespace, error: str) -> None:
    if args.json:
        print(json.dumps({"error": error}))
    else:
        print(error, file=sys.stderr)
    raise SystemExit(1)


def proposed(args: argparse.Namespace, where: Path) -> Path:
    if not where.is_file():
        _fail(args, f"No layout at {where}; `lemonaid grove propose {where}` starts one")
    return where


def _cmd_propose(args: argparse.Namespace) -> None:
    if args.file.exists() and not args.force:
        _fail(args, f"{args.file} exists; pass --force to start it afresh")

    state.save(state.load(), args.file)
    grove = live.fresh(load_config(), None, where=args.file)
    if args.json:
        print(json.dumps({"layout": str(args.file), "blocks": len(grove.blocks), "error": None}))
    else:
        print(f"Proposed layout at {args.file}, from the live grove's {len(grove.blocks)} blocks")


def _cmd_apply(args: argparse.Namespace) -> None:
    proposed(args, args.file)
    try:
        wanted = json.loads(args.file.read_text())
    except (OSError, json.JSONDecodeError) as error:
        _fail(args, f"Can't read {args.file}: {error}")
        raise
    if not isinstance(wanted, dict) or not isinstance(wanted.get("plots"), dict):
        _fail(args, f"{args.file} isn't a grove layout: it has no plots")

    config = load_config()
    found = live.current_blocks(config, None)
    done: list[proposal.Applied] = []

    def change(saved: dict) -> dict:
        # Laid out first, so a group the proposal placed but the saved layout hasn't seen yet
        # isn't taken for one that ended.
        switched = landmarks.with_packhouse(saved, config.tui.grove_packhouse)
        done.append(proposal.apply(arrange.arrange(found, switched)[1], wanted, found))
        return done[-1].layout

    try:
        state.update(change)
    except edit.EditError as error:
        _fail(args, f"Not applied: {error}")
    applied = done[-1]
    if args.json:
        print(
            json.dumps(
                {
                    "applied": applied.applied,
                    "skipped": applied.skipped,
                    "kept": applied.kept,
                    "error": None,
                }
            )
        )
        return

    print(f"Applied {len(applied.applied)} plots from {args.file}")
    if applied.skipped:
        print(f"Skipped, gone from the grove: {', '.join(applied.skipped)}")
    if applied.kept:
        print(f"Kept where they are, new since the proposal: {', '.join(applied.kept)}")


def add_parsers(grove_subparsers: argparse._SubParsersAction) -> None:
    propose = grove_subparsers.add_parser(
        "propose", help="Copy the live layout to FILE, to rearrange with --layout FILE"
    )
    propose.add_argument("file", type=Path)
    propose.add_argument("--force", action="store_true", help="Replace FILE if it exists")
    propose.add_argument("--json", action="store_true", help="Print the result as JSON")
    propose.set_defaults(func=_cmd_propose)

    apply = grove_subparsers.add_parser(
        "apply", help="Give the live grove's blocks the plots in proposed layout FILE"
    )
    apply.add_argument("file", type=Path)
    apply.add_argument("--json", action="store_true", help="Print the result as JSON")
    apply.set_defaults(func=_cmd_apply)
