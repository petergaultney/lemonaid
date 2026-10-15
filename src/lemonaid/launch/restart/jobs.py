"""Recognize direct native helpers without admitting their tool-job descendants."""

import dataclasses
from pathlib import Path

from ...claude import launch_args
from . import process


def helpers(
    source: process.Identity, harness: str, children: list[process.Identity]
) -> list[process.Identity]:
    found = []
    for child in children:
        if child.parent != source.pid:
            continue
        argv = launch_args.argv(child.pid)
        if not argv:
            continue
        # Claude 2.1.300's direct sleep inhibitor exits on native SIGTERM; it is
        # distinct from shell/tool children. Multiple matching children are ambiguous.
        if (
            harness == "claude"
            and argv == ["caffeinate", "-i", "-t", "300"]
            and launch_args.executable(child.pid) == "/usr/bin/caffeinate"
        ):
            found.append(child)
        if harness == "codex":
            expected = Path(source.executable).parent.parent / "bin/codex-code-mode-host"
            if (
                Path(child.executable) == expected
                and Path(argv[0]) == expected
                and Path(launch_args.executable(child.pid)) == expected
            ):
                found.append(child)
    return [] if harness == "claude" and len(found) > 1 else found


def saved(plan: dict) -> set[int]:
    source = process.Identity(**plan["source"])
    identities = [process.Identity(**entry) for entry in plan.get("helpers", [])]
    current = helpers(
        source, plan["harness"], [entry for entry in identities if process.same(entry)]
    )
    if [dataclasses.asdict(entry) for entry in current] != plan.get("helpers", []):
        raise ValueError("Native helper generation changed after preflight")
    return {entry.pid for entry in current}
