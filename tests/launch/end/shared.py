from pathlib import Path

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.lineage import links

PR = "https://github.com/o/r/pull/12"
OTHER_PR = "https://github.com/o/r/pull/13"


def prs(*urls: str) -> str:
    rows = "".join(f"| Review | [r#{u.rsplit('/', 1)[1]}]({u}) | |\n" for u in urls)
    return f"## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n{rows}"


def lemon(
    name: str,
    status: str = "",
    body: str = "",
    channel: str = "",
    parent: str = "",
    session: str = "",
) -> tuple[str, Path]:
    """A lemon with a brief, attached to *channel* when one is given, in tmux *session*."""
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "".join(
        [f"Status: {status}\n" if status else "", f"Parent: {parent}\n" if parent else ""]
    )
    path.write_text(f"# {name}\n\n{header}\n{body}")
    with db.connect() as conn:
        if channel:
            metadata = {"cwd": str(path.parent), **({"tmux_session": session} if session else {})}
            db.add(conn, channel, "", metadata=metadata)
            attached.attach(conn, channel, path)
        return identity.ensure(conn, path), path


def link(child: str, parent: str) -> None:
    with db.connect() as conn:
        links.set_parent(conn, child, parent)


def archive_card(channel: str) -> None:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        assert row is not None
        db.archive(conn, row.id)
