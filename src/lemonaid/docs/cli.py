"""`lemonaid docs`: the docs a lemon was given (or, for those its mode only logs, would be), the
lemons holding a doc, and every doc's package and triggers.

  lemonaid docs SESSION      a session's context windows and what each was given;
                             SESSION is a session ID, a prefix of one, or a channel
  lemonaid docs --self       the same for the calling lemon
  lemonaid docs who DOC      the live lemons whose current window holds DOC, a path
                             or a file name (--all includes lemons that ended)
  lemonaid docs table        every package and every doc with a package or triggers,
                             as Markdown tables, from the docs under [docs] roots
  lemonaid docs mode SESSION [classic|packages]
                             a session's docs mode, or change it; --self for the
                             calling lemon. A change takes effect at the session's
                             next start, as it says.
"""

import argparse
import os
import sys
from collections import abc
from pathlib import Path

from .. import brief
from ..config import load_config
from ..inbox import db
from ..inbox.channel import channel_id, full_channel_id
from . import deliveries, index, lemons, mode_cli, paths, views


def _sessions(log: abc.Iterable[dict]) -> dict[tuple[str, str], list[dict]]:
    found: dict[tuple[str, str], list[dict]] = {}
    for entry in log:
        found.setdefault((str(entry.get("harness")), str(entry.get("session"))), []).append(entry)
    return found


def _current(entries: abc.Sequence[dict]) -> list[dict]:
    """The entries of the session's latest window."""
    latest = max((e.get("window") or 0 for e in entries), default=0)
    return [e for e in entries if (e.get("window") or 0) == latest]


def _missing(entries: abc.Sequence[dict]) -> list[str]:
    """The packages for the lemon now that its latest window wasn't given."""
    started = [e for e in _current(entries) if e.get("kind") == "window"]
    if not started:
        return []

    config, cwd = load_config(), Path(started[-1].get("cwd") or ".")
    text = lemons.attached_brief(started[-1]["harness"], started[-1]["session"])
    lemon = lemons.Lemon(
        cwd,
        text,
        lemons.on_default_branch(config.docs.default_branch_check, cwd),
        *lemons.kin(lemons.lemon_id(text)),
    )
    given = started[-1].get("packages") or []
    return [p for p in lemons.packages(index.read(paths.index()), lemon) if p not in given]


def _show(wanted: str) -> None:
    session = wanted.split(":", 1)[-1]
    found = {k: v for k, v in _sessions(deliveries.read()).items() if k[1].startswith(session)}
    if len(found) != 1:
        sys.exit(
            f"{len(found)} sessions in {paths.deliveries()} match {wanted!r}"
            + (f": {', '.join(s for _, s in found)}" if found else "")
        )

    entries = next(iter(found.values()))
    print("\n".join(views.session(entries, _missing(entries))))


def _same_doc(wanted: str) -> abc.Callable[[str], bool]:
    if os.sep not in wanted:
        return lambda path: wanted in (Path(path).name, Path(path).stem)

    target = Path(wanted).expanduser().resolve()
    return lambda path: Path(path).resolve() == target


def _channel(harness: str, session: str) -> str:
    return (
        channel_id(harness, session) if harness == "claude" else full_channel_id(harness, session)
    )


def _who(wanted: str, everyone: bool) -> None:
    same = _same_doc(wanted)
    with db.connect() as conn:
        live = set(brief.attached.live_channels(conn))
    rows = []
    for (harness, session), entries in _sessions(deliveries.read()).items():
        window = _current(entries)
        held = [
            e
            for e in window
            if e.get("kind") == "doc"
            and not e.get("shadow")
            and e.get("delivery") != "pointer"
            and same(str(e.get("doc")))
        ]
        if held and (everyone or _channel(harness, session) in live):
            rows.append(
                (next((e for e in window if e.get("kind") == "window"), held[-1]), held[-1])
            )
    print("\n".join(views.holders(rows)) or f"No {'' if everyone else 'live '}lemon holds {wanted}")


def _run(args: argparse.Namespace) -> None:
    words = [w for w in args.words if w not in ("--self", "--all")]
    args.self = args.self or "--self" in args.words
    args.all = args.all or "--all" in args.words
    if words[:1] == ["mode"]:
        mode_cli.run(words[1:], args.self)
    elif words[:1] == ["table"]:
        print("\n".join(views.table(index.build(load_config().docs.roots, paths.index()))))
    elif words[:1] == ["who"] and len(words) == 2:
        _who(words[1], args.all)
    elif args.self and not words:
        session = os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
        if not session:
            sys.exit("--self needs CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID")
        _show(session)
    elif len(words) == 1 and words[0] not in ("who", "table", "mode"):
        _show(words[0])
    else:
        sys.exit(__doc__)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "docs",
        help="The docs a lemon was given, who holds a doc, every doc's triggers, and its mode",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "words",
        nargs=argparse.REMAINDER,  # so a flag may follow them: `docs mode --self classic`
        metavar="SESSION | who DOC | table | mode [SESSION] [MODE]",
    )
    parser.add_argument("--self", action="store_true", help="the calling lemon's session")
    parser.add_argument("--all", action="store_true", help="with who: lemons that ended too")
    parser.set_defaults(func=_run)
