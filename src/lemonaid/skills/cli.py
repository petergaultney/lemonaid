"""`lemonaid skills install`: install lemonaid's packaged skills for Claude and Codex.

Each skill is the packaged SKILL.md plus an optional user file in
`~/.lemons/skills/<name>/`: `overlay.md` is appended, `SKILL.md` replaces the packaged
text. The result is written once to lemonaid's state directory, and each harness's skill
entry is a symlink to it. An entry lemonaid didn't create is never replaced.

    lemonaid skills install                      # every packaged skill, every harness found
    lemonaid skills install watch-pr --harness codex
    lemonaid skills install --print watch-doc    # the text, for installing it yourself
"""

import argparse
import json
import pathlib
import sys

from . import compose, install


def _harnesses(chosen: list[str]) -> dict[str, pathlib.Path]:
    """The chosen harnesses, or by default every harness whose home directory exists."""
    dirs = install.harness_skill_dirs()
    return {h: d for h, d in dirs.items() if h in chosen or (not chosen and d.parent.is_dir())}


def _render_all(names: list[str]) -> list[compose.Rendered]:
    try:
        return [
            compose.render(compose.PACKAGED_DIR, compose.default_user_dir(), name)
            for name in names or compose.packaged_names(compose.PACKAGED_DIR)
        ]
    except compose.Problem as e:
        print(e, file=sys.stderr)
        sys.exit(2)


def _cmd_install(args: argparse.Namespace) -> None:
    if args.print:
        if len(args.names) != 1:
            args.parser.error("--print takes exactly one skill name")
        print(_render_all(args.names)[0].text, end="")
        return

    harnesses = _harnesses(args.harness)
    if not harnesses:
        print(
            "no harness found (no ~/.claude or ~/.codex); pass --harness to create one",
            file=sys.stderr,
        )
        sys.exit(1)

    rendered_dir = install.default_rendered_dir()
    report, unmanaged = [], False
    for r in _render_all(args.names):
        try:
            skill_dir = install.write_rendered(rendered_dir, r.name, r.text)
        except install.Unmanaged as e:
            print(f"{r.name}: refused: {e}", file=sys.stderr)
            unmanaged = True
            continue

        report.append(
            (
                r,
                skill_dir,
                [install.link(h, d / r.name, skill_dir, r.text) for h, d in harnesses.items()],
            )
        )

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "skill": r.name,
                        "source": r.source,
                        "rendered": str(skill_dir),
                        "harnesses": [
                            {
                                "harness": x.harness,
                                "entry": str(x.entry),
                                "outcome": x.outcome.name.lower(),
                                "detail": x.detail,
                            }
                            for x in results
                        ],
                    }
                    for r, skill_dir, results in report
                ],
                indent=2,
            )
        )
    else:
        for r, skill_dir, results in report:
            print(f"{r.name}: {r.source} -> {skill_dir}")
            for x in results:
                print(
                    f"  {x.harness}: {x.outcome.value} {x.entry}"
                    + (f": {x.detail}" if x.detail else "")
                )
    refused = any(x.outcome is install.Outcome.REFUSED for _, _, results in report for x in results)
    sys.exit(1 if refused or unmanaged else 0)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("skills", help="Install lemonaid's skills for Claude and Codex")
    sub = parser.add_subparsers(dest="skills_command", required=True)
    ap = sub.add_parser(
        "install",
        help="Write packaged skills, with your overlays, into each harness's skills directory",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("names", nargs="*", metavar="NAME", help="skills to install (default: all)")
    ap.add_argument(
        "--harness",
        action="append",
        default=[],
        choices=sorted(install.harness_skill_dirs()),
        help="install only for this harness, creating its skills directory (repeatable)",
    )
    ap.add_argument("--print", action="store_true", help="print one skill's text instead")
    ap.add_argument("--json", action="store_true", help="report as JSON")
    ap.set_defaults(func=_cmd_install, parser=ap)
