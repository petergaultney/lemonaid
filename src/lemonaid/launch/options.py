"""Shared launch arguments and side-effect-free command inspection."""

import argparse
import dataclasses
import json
import shlex
import sys
from pathlib import Path

from ..brief import store
from ..config import TmuxSessionConfig, load_config
from . import command, handoff, resolve


def _describe_passthrough(parser: argparse.ArgumentParser) -> None:
    parser.epilog = "Put lemonaid options before --; all arguments after it pass to the lemon, following preset defaults."


def _extra(args: argparse.Namespace) -> list[str]:
    return [*getattr(args, "lemon_arg", ()), *getattr(args, "lemon_args", ())]


def add_arguments(parser: argparse.ArgumentParser, dry_run: bool = True) -> None:
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--harness",
        default="default",
        metavar="NAME",
        help="Legacy template name, preset name, or harness executable",
    )
    selector.add_argument("--preset", default="", metavar="NAME", help="Named lemon preset")
    parser.add_argument("--shape", default="", metavar="NAME", help="Independent session shape")
    parser.add_argument(
        "--lemon-arg",
        action="append",
        default=[],
        metavar="TOKEN",
        help="Append a harness argument (repeatable; use --lemon-arg=--flag)",
    )
    if dry_run:
        parser.add_argument(
            "--dry-run", action="store_true", help="Show the launch without starting anything"
        )
    _describe_passthrough(parser)


def selected(config: TmuxSessionConfig, args: argparse.Namespace) -> resolve.Resolved:
    return resolve.resolve(
        config,
        args.harness,
        getattr(args, "preset", ""),
        getattr(args, "shape", ""),
        _extra(args),
    )


def inspection(
    resolved: resolve.Resolved,
    config: TmuxSessionConfig,
    directory: Path,
    prompt: str = "",
    title: str = "",
) -> dict:
    line, environment = command.harness_line(
        resolved.line, directory, prompt, command.codex_writable_roots(config), title
    )
    windows = list(resolved.windows)
    windows[resolved.lemon_window] = line
    return {
        **dataclasses.asdict(resolved),
        "windows": windows,
        "command": line,
        "environment": environment,
        "directory": str(directory),
    }


def show(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result))
        return

    print(f"Lemon: {result['lemon']}\nShape: {result['shape']}")
    print(f"Directory: {result['directory']}\nLemon slot (zero-based): {result['lemon_window']}")
    for index, line in enumerate(result["windows"]):
        print(f"  {index}: {line or '(shell)'}")
    if result["environment"]:
        print(f"Environment: {json.dumps(result['environment'])}")
    if note := result.get("note"):
        print(note)


def preview(args: argparse.Namespace, config: TmuxSessionConfig) -> bool:
    if not getattr(args, "dry_run", False):
        return False

    path = store.resolve(args.brief) if args.brief else None
    if path and not path.is_file():
        raise ValueError(f"No brief at {path}")
    if (args.name or args.parent or args.group) and not path:
        raise ValueError("--name, --parent and --group need --brief")
    given = handoff.Handoff(brief=path, name=args.name)
    resolved = selected(config, args)
    if not resolved.line.strip() and (getattr(args, "target", "") or path or args.prompt):
        raise ValueError(f"Lemon {resolved.lemon!r} has no harness command")
    result = inspection(
        resolved,
        config,
        Path.cwd(),
        handoff.first_prompt(given, args.prompt),
        handoff.session_title(given),
    )
    result["note"] = "Preview uses the current directory; no directory hook or tmux query was run."
    show(result, args.json)
    return True


def _presets(args: argparse.Namespace) -> None:
    try:
        config = load_config().tmux_session
        if args.preset_command == "show":
            resolved = resolve.resolve(
                config, preset=args.name, shape=args.shape, extra=_extra(args)
            )
            show(
                inspection(resolved, config, Path(args.directory).expanduser().resolve()), args.json
            )
            return

        rows = resolve.entries(config)
        if args.json:
            print(json.dumps(rows))
        else:
            for row in rows:
                line = (
                    row["command"] if row["legacy"] else shlex.join([row["harness"], *row["args"]])
                )
                print(f"{row['name']}: {line}  {row['description']}  {' '.join(row['tags'])}")
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(1)


def add_presets_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("presets", help="List named lemons or inspect a resolved launch")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=_presets, preset_command="")
    show_parser = parser.add_subparsers(dest="preset_command").add_parser(
        "show", help="Resolve a named lemon without launching it"
    )
    show_parser.add_argument("name")
    show_parser.add_argument("--shape", default="")
    show_parser.add_argument("--lemon-arg", action="append", default=[])
    show_parser.add_argument("--directory", default=".")
    show_parser.add_argument("--json", action="store_true")
    _describe_passthrough(show_parser)
    show_parser.set_defaults(func=_presets)
