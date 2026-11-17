"""`lemonaid grove`: the grove map from the command line, for people and lemons."""

__lazy_modules__ = ["lemonaid.grove.source", "lemonaid.grove.tui"]

import argparse
import dataclasses
import json
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.segment import Segment, Segments

from ..config import load_config
from ..lemon_watchers.common import detect_terminal_switch_source
from . import edit_cli, garden_cli, layout_cli
from .draw import block_scene, canvas, scenes
from .layout import advice, arrange, compact, screen_size
from .source import live, standalone
from .tui.frame import Grove


def _grove(save: bool, where: Path | None) -> Grove:
    config = load_config()
    source = detect_terminal_switch_source()
    switch_source = None if source == "unknown" else source
    if save:
        return live.fresh(config, switch_source, where)
    return live.preview(config, switch_source, where)


def _screen(args: argparse.Namespace) -> tuple[int, int]:
    """*args*' size, else the last grove screen's, else the terminal's."""
    grove = screen_size.last()
    if grove:
        return args.width or grove[0], args.height or grove[1]

    size = shutil.get_terminal_size((214, 64))
    return args.width or size.columns, args.height or size.lines - 1


def _as_json(found: tuple, arrangement: arrange.Arrangement, screen: tuple[int, int]) -> dict:
    where = {
        block.name: {p.key: p for p in compact.placed(block, arrangement, screen)}
        for block in found
    }
    return {
        "blocks": [
            {
                "digit": block.digit,
                "group": block.name,
                "plot": dataclasses.asdict(arrangement.plots[block.name]),
                "trees": [
                    {
                        "key": tree.key,
                        "letter": arrangement.trees[(block.name, tree.key)].letter,
                        "label": arrangement.trees[(block.name, tree.key)].label,
                        "spot": [
                            arrangement.trees[(block.name, tree.key)].cx,
                            arrangement.trees[(block.name, tree.key)].cy,
                        ],
                        "lemons": [dataclasses.asdict(lemon) for lemon in tree.lemons],
                        "zoomed": _zoomed(where[block.name].get(tree.key)),
                    }
                    for tree in block.trees
                ],
            }
            for block in found
        ],
        "open": [dataclasses.asdict(plot) for plot in arrangement.open],
        "error": None,
    }


def _zoomed(placed: compact.Placed | None) -> dict | None:
    if placed is None:
        return None

    return {
        "center": list(placed.center),
        "list": list(placed.list),
        "stands": not placed.off,
        "off_stand": placed.off,
    }


def _cmd_show(args: argparse.Namespace) -> None:
    where = layout_cli.proposed(args, args.layout) if args.layout else None
    grove = _grove(not args.dry_run, where)
    found, arrangement = grove.blocks, grove.arrangement
    screen = _screen(args)
    if args.json:
        advised = advice.advise(found, arrangement, screen)
        print(
            json.dumps(
                _as_json(found, arrangement, screen)
                | {"warnings": [a._asdict() for a in advised], "screen": list(screen)}
            )
        )
        return

    chosen = next((block for block in found if block.digit == args.block), None)
    if args.block and chosen is None:
        print(
            f"No block {args.block}; blocks are {', '.join(b.digit for b in found)}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if args.compact:
        if chosen is None:
            print("--compact needs a block's digit", file=sys.stderr)
            raise SystemExit(1)

        print(
            f"Block {chosen.digit} ({chosen.name or 'no group'}) zoomed at {screen[0]}x{screen[1]}"
        )
        print("\n".join(compact.lines(chosen, arrangement, screen)))
        for a in advice.advise(found, arrangement, screen):
            if a.block == chosen.digit:
                print(f"warning {a.block}{a.letter} {a.kind}: {a.reason}")
        return

    picture = canvas.blank(*screen)
    if chosen:
        block_scene.zoomed(picture, chosen, arrangement, phase=0.0)
    else:
        scenes.overview(picture, found, arrangement, phase=0.0)
    off = [p for p in compact.placed(chosen, arrangement, screen) if p.off] if chosen else []
    if off:
        keys = (f"{chosen.digit}{p.letter}" for p in off)
        print(
            f"Trees off their lists at {picture.width}x{picture.height}: {', '.join(keys)}",
            file=sys.stderr,
        )
    if args.plain:
        print("\n".join(canvas.plain_lines(picture)))
        return

    console = Console(
        force_terminal=True, color_system="truecolor", width=picture.width, highlight=False
    )
    for row in picture.rows:
        console.print(Segments([*canvas.line_segments(row), Segment.line()]), end="")


def _cmd_open(_args: argparse.Namespace) -> None:
    source = detect_terminal_switch_source()
    standalone.run(load_config(), None if source == "unknown" else source)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "grove",
        help="The grove map (beta): groups as blocks, places as trees",
        description="Draw the grove the inbox's grove view shows, or print its layout as JSON. "
        "Beta: commands, JSON and layout files may change between releases. See docs/grove.md.",
    )
    grove_subparsers = parser.add_subparsers(dest="grove_command", required=True)
    show = grove_subparsers.add_parser("show", help="Draw the grove, or one block of it")
    show.add_argument("block", nargs="?", default="", help="A block's digit, to draw it zoomed in")
    show.add_argument(
        "--width",
        type=int,
        default=0,
        help="Columns to draw (default: the grove screen's last size, else the terminal's)",
    )
    show.add_argument(
        "--height",
        type=int,
        default=0,
        help="Rows to draw (default: the grove screen's last size, else the terminal's)",
    )
    show.add_argument(
        "--compact",
        action="store_true",
        help="With a block's digit: each tree's spot, trunk and list position, and its warnings, "
        "as a few lines of text",
    )
    show.add_argument("--plain", action="store_true", help="Characters only, without color")
    show.add_argument("--dry-run", action="store_true", help="Don't save new plots or spots")
    show.add_argument(
        "--json", action="store_true", help="Print the blocks, trees and lemons as JSON"
    )
    show.add_argument(
        "--layout",
        type=Path,
        metavar="FILE",
        help="Draw the proposed layout in FILE (from `grove propose`) instead of the live one",
    )
    show.set_defaults(func=_cmd_show)
    grove_subparsers.add_parser(
        "open", help="Open the grove full-screen here; choosing a lemon switches to it"
    ).set_defaults(func=_cmd_open)
    edit_cli.add_parsers(grove_subparsers)
    garden_cli.add_parsers(grove_subparsers)
    layout_cli.add_parsers(grove_subparsers)
