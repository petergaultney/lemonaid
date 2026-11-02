#!/usr/bin/env python3
"""Categorize a git diff by file purpose and Python line content."""

import argparse
import subprocess
import sys

from . import categorize, collect, report


def _collect_stats(base: str) -> dict[str, dict]:
    result = subprocess.run(
        ["git", "diff", "--numstat", f"{base}...HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"git diff failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    numstats: list[tuple[str, int, int]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 3:
            print(f"warning: unexpected numstat line (skipping): {line!r}", file=sys.stderr)
            continue

        added_s, removed_s, filepath = parts
        filepath = categorize.normalize_rename(filepath)
        added = int(added_s) if added_s != "-" else 0
        removed = int(removed_s) if removed_s != "-" else 0

        numstats.append((filepath, added, removed))

    cats, warnings = collect.collect_categories(base, numstats, categorize.categorize, report.CAT_NAMES)
    for warning in warnings:
        print(f"warning: {warning}; counting all lines as code", file=sys.stderr)

    return cats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Categorize a git diff by file purpose and Python line content.",
    )
    parser.add_argument(
        "base",
        nargs="?",
        default="main",
        help="base ref to diff against (default: main)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        metavar="NUM",
        help="update this GitHub PR description with the diff breakdown",
    )
    args = parser.parse_args()

    cats = _collect_stats(args.base)
    print(report.format_report(cats, args.base))
    if args.pr:
        report.update_pr(args.pr, report.format_pr_section(cats))


if __name__ == "__main__":
    main()
