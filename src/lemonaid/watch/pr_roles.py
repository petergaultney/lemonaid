"""The role a lemon holds on each PR it watches: a PR its child authors makes it the parent."""

from pathlib import Path

from ..brief import lemon
from ..config import load_config
from ..inbox import db
from ..lineage import links
from ..log import get_logger
from . import roles, subscriptions

_log = get_logger("watch.pr_roles")


def _authored(text: str, cwd: Path, vaults: tuple[Path, ...]) -> frozenset[tuple[str, ...]]:
    """The PRs a brief holds as their author; it is read without its own children."""
    return frozenset(
        spec.target
        for spec in subscriptions.report(text, cwd, vaults=vaults).specs
        if spec.kind == "pr" and spec.role == roles.AUTHOR
    )


def children_author(
    lemon_id: str, cwd: Path, vaults: tuple[Path, ...]
) -> frozenset[tuple[str, ...]]:
    with db.connect() as conn:
        briefs = [
            lemon.brief_of(conn, child)
            for child in links.children_of(conn, lemon.current(conn, lemon_id))
        ]
    found: frozenset[tuple[str, ...]] = frozenset()
    for path in filter(None, briefs):
        try:
            found |= _authored(path.read_text(), cwd, vaults)
        except FileNotFoundError:
            continue
        except OSError as error:
            _log.warning("Cannot read child brief %s: %s", path, error)
    return found


def status(brief: Path, lemon_id: str) -> list[str]:
    """One line per PR the brief watches, naming the role that decides what wakes it."""
    vaults = tuple(load_config().brief.vaults)
    children = children_author(lemon_id, Path.cwd(), vaults)
    return [
        f"{repo}#{number}: woken as its {spec.role}"
        for spec in subscriptions.report(
            brief.read_text(), Path.cwd(), lemon_id, vaults, children
        ).specs
        if spec.kind == "pr"
        for repo, number in [spec.target]
    ]
