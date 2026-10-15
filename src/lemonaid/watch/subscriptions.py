"""Read a brief's watch commands and its automatic subscriptions without executing shell text."""

import argparse
import dataclasses
import re
import shlex
from pathlib import Path

from ..brief import doc_table, identity, lemon_table, pr_table, sections, waiters
from . import briefs_cli, doc_cli, file_cli, pr_cli, repo_cli


class Problem(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Problem(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise Problem(message or "Use a watch command, not --help")


@dataclasses.dataclass(frozen=True)
class Subscription:
    kind: str
    target: tuple[str, ...]
    me: str = ""
    legacy: tuple[str, ...] = ()
    interval: float = 5
    quiet: float = 2
    edits: bool = False
    head: str = ""
    comments: bool = False
    ci: bool = False
    to: frozenset[str] = frozenset({"merge", "done"})
    orphans: bool = False
    ignore_removed: bool = False
    skip_outdated: bool = False
    skip_resolved: bool = False
    labels: tuple[str, ...] = ()
    exclude_authors: tuple[str, ...] = ()
    pushes: bool = False
    state_dir: Path | None = None
    lemons: tuple[lemon_table.Row, ...] = ()
    needs: bool = False

    @property
    def source(self) -> str:
        return f"{self.kind}: {', '.join(self.target)}"

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        return self.kind, self.target


def _parse(command: str, parent: str, me: str, cwd: Path) -> Subscription | None:
    command = re.sub(r"--head\s+<[^>]+>", "", command)
    words = shlex.split(command)
    if words[:3] in [
        ["lemonaid", "inbox", "watch"],
        ["lemonaid", "wait", "--self"],
        ["lemonaid", "watch", "--self"],
    ]:
        return None

    if words[:2] != ["lemonaid", "watch"]:
        raise Problem(f"Not a lemonaid watch subscription: {command}")

    parser = _Parser(allow_abbrev=False)
    sub = parser.add_subparsers(dest="kind", required=True)
    for module in (doc_cli, file_cli, pr_cli, repo_cli, briefs_cli):
        module.add_parser(sub)
    args = parser.parse_args(words[2:])
    if args.status or not getattr(args, "wait", True):
        raise Problem(f"Use the --wait form: {command}")

    kind = args.kind
    if kind == "pr":
        repo, number = args.wait
        repo = repo or args.repo
        if not repo:
            raise Problem("PR subscriptions need a URL or --repo owner/name")
        target = (repo, str(number))
    elif kind == "repo":
        target = (args.wait,)
    elif kind == "briefs":
        target = (parent if args.use_self else args.lemon,)
    else:
        paths = args.wait if kind == "file" else [args.wait]
        target = tuple(str((cwd / path.expanduser()).resolve()) for path in paths)
    values = {
        name: getattr(args, name)
        for name in (
            "interval",
            "quiet",
            "edits",
            "head",
            "comments",
            "ci",
            "orphans",
            "ignore_removed",
            "skip_outdated",
            "skip_resolved",
            "pushes",
            "state_dir",
        )
        if hasattr(args, name) and getattr(args, name) is not None
    }
    if kind == "repo":
        values["labels"], values["exclude_authors"] = tuple(args.label), tuple(args.exclude_author)
    values["to"] = (
        frozenset(args.to or briefs_cli.CHILD_TO) if kind == "briefs" else Subscription.to
    )
    return Subscription(kind, target, args.me or me, tuple(getattr(args, "legacy", ())), **values)


@dataclasses.dataclass(frozen=True)
class Reading:
    specs: tuple[Subscription, ...]
    problems: tuple[str, ...]


def report(text: str, cwd: Path, owner: str = "", vaults: tuple[Path, ...] = ()) -> Reading:
    problems = []
    try:
        parent = identity.read(text) or owner
    except ValueError as error:
        parent = owner
        problems.append(str(error))
    me = f"Author ({parent.rsplit('.', 1)[-1]})"
    specs: dict[tuple[str, tuple[str, ...]], Subscription] = {}
    for command in waiters.commands(text):
        try:
            spec = _parse(command, parent, me, cwd)
        except (ValueError, TypeError) as error:
            problems.append(f"{command}: {error}")
            continue

        if spec and all(spec.target):
            specs[spec.key] = spec
    for section in sections.behavior(text):
        if section.heading.lower() == "prs":
            rows, errors = pr_table.parse(section.body)
            problems.extend(errors)
            for row in rows:
                if found := pr_table.target(row.pr):
                    key = ("pr", found)
                    old = specs.get(key, Subscription("pr", found, me, interval=60))
                    specs[key] = dataclasses.replace(old, comments=True, ci=True)
                if path := doc_table.path_of(row.review, vaults):
                    key = ("doc", (str(path.resolve()),))
                    specs.setdefault(key, Subscription("doc", key[1], me, quiet=20))
        elif section.heading.lower() == "docs":
            problems.extend(doc_table.parse(section.body)[1])
        elif section.heading.lower() == "lemons":
            problems.extend(lemon_table.parse(section.body)[1])
    for row in doc_table.rows(text):
        key = ("doc", (str(row.path),))
        old = specs.get(key, Subscription("doc", key[1], me, quiet=20))
        specs[key] = dataclasses.replace(
            old, edits=old.edits or row.watch == doc_table.Watch.ALL_EDITS
        )
    if parent:
        key = ("briefs", (parent,))
        specs[key] = dataclasses.replace(
            specs.get(key) or Subscription("briefs", (parent,), me),
            lemons=tuple(lemon_table.rows(text)),
            needs=True,
        )
    return Reading(tuple(specs.values()), tuple(problems))


def read(
    text: str, cwd: Path, owner: str = "", vaults: tuple[Path, ...] = ()
) -> list[Subscription]:
    return list(report(text, cwd, owner, vaults).specs)
