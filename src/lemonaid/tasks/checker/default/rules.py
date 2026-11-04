"""The default checker: a starting policy, run as `python -m lemonaid.tasks.checker.default`.

`DEFAULT` is its rule set, combined as `compose` describes. A checker of your own can
import it, change a stage, and call `main` with the result.

Lemonaid ships it so replay has a checker to run; a user's own package replaces it. It
reads only the line protocol.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from .. import checker_input, protocol, stream
from . import (
    closing,
    compose,
    coverage,
    holders,
    idle,
    needs_claims,
    recheck,
    settings,
    starts,
    status_claims,
    waits,
)


def pr_claims(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    """A Status, or a `done`, that the task's PR contradicts; see `status_claims`."""
    return status_claims.contradicted(view, brief)


def _watches(view: checker_input.View) -> list[tuple[str, str]]:
    if view.kind == "brief":
        return [("lemon", view.subject), ("brief", view.subject)]

    holder = view.fields.get("holder", "")
    if view.fields.get("lifecycle") == "closed":
        return [
            ("task", view.subject),
            *([("pr", view.fields["subject_url"])] if view.fields.get("subject_url") else []),
            *([("lineage", view.fields["closed.by"])] if view.fields.get("closed.by") else []),
        ]

    return [
        ("task", view.subject),
        *(
            (kind, holder.removeprefix("brief:"))
            for kind in ("lemon", "brief")
            if holder.startswith("brief:")
        ),
        *([("pr", view.fields["subject_url"])] if view.fields.get("subject_url") else []),
        *(
            ("lineage", who)
            for who in (view.fields.get("assignment.by", ""), view.fields.get("holder_parent", ""))
            if who
        ),
        *(
            ("task", f.removeprefix("dependency."))
            for f in view.fields
            if f.startswith("dependency.")
        ),
    ]


DEFAULT = compose.Rules(
    absent=(holders.unavailable, starts.unstarted),
    claims=(pr_claims, needs_claims.unsupported),
    waits=(waits.findings,),
    declared=(waits.declared,),
    idle=(idle.challenge,),
    closed=(closing.evaluate,),
    uncovered=(coverage.evaluate,),
    watches=(_watches,),
    asks=(recheck.findings,),
)


def evaluate(view: checker_input.View, rules: compose.Rules = DEFAULT) -> list[protocol.Record]:
    """The complete finding set for the input's task."""
    return compose.task(rules, view)


def respond(operation: str, text: str, rules: compose.Rules = DEFAULT) -> str:
    """The output for one `describe` or `evaluate` input; raises ValueError for a malformed
    input or an unknown operation."""
    view = checker_input.read(text)
    if operation == "describe":
        return protocol.render(("watch", *w) for w in compose.watches(rules, view))

    if operation != "evaluate":
        raise ValueError(f"unknown operation {operation!r}")

    return protocol.render(
        compose.brief(rules, view) if view.kind == "brief" else compose.task(rules, view)
    )


def main(argv: abc.Sequence[str] | None = None, rules: compose.Rules = DEFAULT) -> None:
    """`describe` or `evaluate` one `--input` file, or `serve` requests on stdin."""
    parser = argparse.ArgumentParser(prog="lemonaid.tasks.checker.default")
    parser.add_argument("operation", choices=("describe", "evaluate", "serve"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    if args.operation == "serve":
        stream.serve(lambda operation, text: respond(operation, text, rules), sys.stdin, sys.stdout)
        return

    if args.input is None:
        parser.error(f"{args.operation} needs --input")

    sys.stdout.write(respond(args.operation, args.input.read_text(), rules))
