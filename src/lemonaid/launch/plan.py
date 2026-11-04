"""What `lemon start` types into a new shell, and the environment it starts the shell with."""

import argparse
import dataclasses
from pathlib import Path

from .. import launch_token
from ..config import Config
from . import command, handoff, options


@dataclasses.dataclass(frozen=True)
class Plan:
    harness: str
    given: handoff.Handoff
    typed: str  # the line typed into the new shell
    environment: dict[str, str]  # the new shell's
    token: str  # the launch token a waiting brief is keyed on; "" without --brief


def plan(args: argparse.Namespace, config: Config, directory: Path) -> tuple[Plan | None, str]:
    """What to type, and with which environment, to start the lemon *args* asks for."""
    try:
        resolved = options.selected(config.tmux_session, args)
    except ValueError as error:
        return None, str(error)

    if not resolved.line.strip():
        return None, f"Lemon {resolved.lemon!r} has no harness command"

    given, error = handoff.prepare(args.brief, args.parent, args.name, tuple(args.group))
    if error:
        return None, error

    if given.brief and (error := command.unclaimable(resolved.line)):
        return None, error

    typed, environment = command.harness_line(
        resolved.line,
        directory,
        handoff.first_prompt(given, args.prompt),
        command.codex_writable_roots(config.tmux_session),
        handoff.session_title(given),
    )
    token = launch_token.new() if given.brief else ""
    return Plan(
        resolved.lemon,
        given,
        typed,
        {**environment, **({launch_token.ENV: token} if token else {})},
        token,
    ), ""


def result(plan: Plan, directory: Path, **where: str) -> dict:
    given = plan.given
    return {
        **where,
        "dir": str(directory),
        "harness": plan.harness,
        "brief": str(given.brief) if given.brief else None,
        "lemon_id": given.link[0] if given.link else None,
        "parent": given.link[1] if given.link else None,
        "groups": list(given.groups),
        "name": given.name or None,
    }
