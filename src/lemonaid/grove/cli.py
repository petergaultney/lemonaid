"""`lemonaid grove`: the grove map from the command line, for people and lemons."""

__lazy_modules__ = ["lemonaid.grove.source", "lemonaid.grove.tui"]

import argparse
import dataclasses
import json
import shutil
import sys

from rich.console import Console
from rich.segment import Segment, Segments

from ..config import load_config
from ..lemon_watchers.common import detect_terminal_switch_source
from . import edit_cli
from .draw import block_scene, canvas, scenes
from .layout import arrange
from .source import live, standalone
from .tui.frame import Grove


def _grove(save: bool) -> Grove:
    config = load_config()
    source = detect_terminal_switch_source()
    switch_source = None if source == "unknown" else source
    return live.fresh(config, switch_source) if save else live.preview(config, switch_source)


def _as_json(found: tuple, arrangement: arrange.Arrangement) -> dict:
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
                    }
                    for tree in block.trees
                ],
            }
            for block in found
        ],
        "open": [dataclasses.asdict(plot) for plot in arrangement.open],
        "error": None,
    }


def _cmd_show(args: argparse.Namespace) -> None:
    grove = _grove(save=not args.dry_run)
    found, arrangement = grove.blocks, grove.arrangement
    if args.json:
        print(json.dumps(_as_json(found, arrangement)))
        return

    size = shutil.get_terminal_size((214, 64))
    picture = canvas.blank(args.width or size.columns, args.height or size.lines - 1)
    chosen = next((block for block in found if block.digit == args.block), None)
    if args.block and chosen is None:
        print(
            f"No block {args.block}; blocks are {', '.join(b.digit for b in found)}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if chosen:
        block_scene.zoomed(picture, chosen, arrangement, phase=0.0)
    else:
        scenes.overview(picture, found, arrangement, phase=0.0)
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
        "--width", type=int, default=0, help="Columns to draw (default: the terminal's)"
    )
    show.add_argument(
        "--height", type=int, default=0, help="Rows to draw (default: the terminal's)"
    )
    show.add_argument("--plain", action="store_true", help="Characters only, without color")
    show.add_argument("--dry-run", action="store_true", help="Don't save new plots or spots")
    show.add_argument(
        "--json", action="store_true", help="Print the blocks, trees and lemons as JSON"
    )
    show.set_defaults(func=_cmd_show)
    grove_subparsers.add_parser(
        "open", help="Open the grove full-screen here; choosing a lemon switches to it"
    ).set_defaults(func=_cmd_open)
    edit_cli.add_parsers(grove_subparsers)
