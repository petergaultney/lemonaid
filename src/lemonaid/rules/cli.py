"""`lemonaid rules`: check and promote the pattern file the end-of-turn check reads, and
replay its patterns over past transcripts before they go live."""

import argparse
import collections
import datetime as dt
import sys
from pathlib import Path

from ..config import load_config
from ..inbox import snooze_time
from . import checks, end_of_turn, patterns, report, snapshot, transcripts


def _pattern_file(given: str) -> Path:
    if given:
        return Path(given).expanduser()

    configured = load_config().rules.patterns
    if configured is None:
        sys.exit("No pattern file: set [rules] patterns in lemonaid's config, or pass --file")
    return configured


def _check(a: argparse.Namespace) -> None:
    source = _pattern_file(a.file)
    parsed = patterns.load(source)
    found = [*parsed.problems, *checks.problems(parsed.patterns)]
    if found:
        sys.exit("\n".join([f"{source}:", *(f"- {problem}" for problem in found)]))

    modes = ", ".join(f"{pattern.id} ({pattern.mode})" for pattern in parsed.patterns)
    print(f"{source}: every check passes for {modes}")
    if not a.promote:
        return

    print(
        f"Promoted to {snapshot.promote(source, parsed.patterns, dt.datetime.now().astimezone())}"
    )
    configured = load_config().rules.patterns
    if configured is None or configured.resolve() != source.resolve():
        print(
            "lemonaid's config doesn't name this file in [rules] patterns, "
            "so the end-of-turn check won't read these patterns"
        )


def _chosen(source: Path, ids: list[str]) -> list[patterns.Pattern]:
    parsed = patterns.load(source)
    listed = "\n".join([f"{source}:", *(f"- {problem}" for problem in parsed.problems)])
    if unknown := sorted(set(ids) - {pattern.id for pattern in parsed.patterns}):
        sys.exit(
            f"{listed}\nno pattern {', '.join(unknown)} to replay"
            if parsed.problems
            else f"{source} has no pattern {', '.join(unknown)}"
        )
    if not parsed.patterns:
        sys.exit(listed)
    if parsed.problems:
        print(f"{listed}\nThose patterns are left out.", file=sys.stderr)
    chosen = [pattern for pattern in parsed.patterns if not ids or pattern.id in ids]
    for pattern in chosen:
        if problem := checks.regex_problem(pattern.regex):
            sys.exit(f"{pattern.id}: {problem}")
    return chosen


def _replay(a: argparse.Namespace) -> None:
    seconds = snooze_time.parse_duration(a.since)
    if seconds is None:
        sys.exit(f'--since must be a duration such as "14d" or "12h", not {a.since!r}')

    chosen = _chosen(_pattern_file(a.file), a.ids)
    since = dt.datetime.now().astimezone() - dt.timedelta(seconds=seconds)
    running, found, stopped, scanned = list(chosen), [], {}, 0
    for said in transcripts.turn_ends(since):
        scanned += 1
        text = end_of_turn.capped(said.text)
        checked = end_of_turn.matches(running, text, said.cwd)
        found.extend((said, pattern, match, text) for pattern, match in checked.found)
        for pattern in checked.too_slow:
            stopped[pattern.id] = said
            running.remove(pattern)

    for said, pattern, match, text in sorted(found, key=lambda hit: hit[0].at):
        print(f"{pattern.id}  {said.at:%Y-%m-%d %H:%M}  {said.harness}  {said.cwd}")
        print(f"  {report.excerpt(text, match)}")
        print(f"  {said.transcript}")
    counts = collections.Counter(pattern.id for _, pattern, _, _ in found)
    print(f"\n{scanned:,} end-of-turn messages since {since:%Y-%m-%d %H:%M}:")
    for pattern in chosen:
        print(f"  {pattern.id}: {counts[pattern.id]}")
    for name, said in stopped.items():
        print(
            f"{name} ran out of time on the turn at {said.at:%Y-%m-%d %H:%M} in "
            f"{said.transcript}, which the hook would skip too, and wasn't run after it"
        )


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "rules",
        help="Check and promote the pattern file lemonaid's Stop hook checks final messages "
        "against, and replay patterns over past transcripts",
        description="See docs/rules.md.",
    )
    sub = parser.add_subparsers(dest="rules_command", required=True)
    file_help = "the pattern file, instead of the one [rules] patterns names"

    cp = sub.add_parser("check", help="Run every check on the pattern file; exits 1 on a problem")
    cp.add_argument("--file", default="", help=file_help)
    cp.add_argument(
        "--promote",
        action="store_true",
        help="once every check passes, write the snapshot the end-of-turn check reads",
    )
    cp.set_defaults(func=_check)

    rp = sub.add_parser(
        "replay",
        help="List what patterns would have matched in Claude's and Codex's transcripts",
    )
    rp.add_argument("ids", nargs="*", help="pattern ids; every pattern when none are given")
    rp.add_argument("--since", default="14d", help='how far back, such as "14d" (the default)')
    rp.add_argument("--file", default="", help=file_help)
    rp.set_defaults(func=_replay)
