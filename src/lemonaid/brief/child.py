"""Child briefs: a dated brief for a lemon not started yet, from a template.

A template contains optional header fields and brief sections, with `$name` placeholders
(Python's `string.Template`; `$$` is a literal `$`). Lemonaid writes the header
above it: the title, `Brief-ID:`, `type: Brief`, `created:`, `Parent:`, `Output-Doc:` when `--output-doc` gives one,
and `Area:` when `--area` gives one.
Packaged templates put the worker sections before the task sections.

`<lemons dir>/brief-templates/<name>.md` replaces the packaged template of that name.
"""

import datetime
import re
import shlex
import string
from collections import abc
from pathlib import Path

from .. import home, obsidian, pr_url
from ..watch import signature
from . import doc_table, identity

PACKAGED_DIR = Path(__file__).parent / "templates"

_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_FLAG_OF = {"pr": "--pr", "output_doc": "--output-doc"}


class Problem(Exception):
    pass


def user_dir() -> Path:
    return home.layout.lemons_dir() / "brief-templates"


def names(packaged_dir: Path, users: Path) -> list[str]:
    return sorted({p.stem for d in (packaged_dir, users) for p in d.glob("*.md")})


def template(packaged_dir: Path, users: Path, name: str) -> str:
    if not _NAME.fullmatch(name):
        raise Problem(f"Template names are lowercase letters, digits and dashes, not {name!r}")

    for directory in (users, packaged_dir):
        if (path := directory / f"{name}.md").is_file():
            return path.read_text()

    raise Problem(
        f"No brief template {name!r} in {users} or packaged; "
        f"there are: {', '.join(names(packaged_dir, users))}"
    )


def pr_values(pr: str, repo: str) -> dict[str, str]:
    """The `$pr_*` values for a PR URL, or a number in *repo* (owner/name)."""
    if parsed := pr_url.parse(pr):
        repo, number = parsed
    elif pr.isdigit() and repo:
        number = pr
    else:
        raise Problem(f"--pr takes a GitHub PR URL, or a number with --repo owner/name: {pr!r}")

    url = f"https://github.com/{repo}/pull/{number}"
    label = f"{repo.rsplit('/', 1)[-1]}#{number}"
    return {
        "pr_url": url,
        "pr_number": number,
        "pr_repo": repo,
        "pr_label": label,
        "pr_link": f"[{label}]({url})",
    }


def output_doc_values(output_doc: str, vaults: abc.Iterable[Path]) -> dict[str, str]:
    path = Path(output_doc).expanduser().absolute()
    url = obsidian.obsidian_url(path, vaults)
    return {
        "output_doc": str(path),
        "output_doc_arg": shlex.quote(str(path)),
        "output_doc_link": f"[{path.stem}]({url})" if url else f"`{path}`",
    }


_HAND_BACK = (
    "You hold the PR's own task, taken from its author. Hand it back to the author once your"
    " verdict is written (`lemonaid task assign TASK_ID --to AUTHOR --reason TEXT`), since the"
    " author acts on it next, and set no status. "
)
_KEEP = (
    "You hold a task of your own, because no lemon's task covers the PR. Keep it, and never"
    " hand it to your parent: set Status `review` while you wait for the author's changes and"
    " `approve` once the PR is clear. Once the maintainer's approving review is on the PR, `approve` is"
    " stale: set `merge`, in every repo. Close the task when the PR merges or closes. "
)


def task_rule(mode: str) -> str:
    """What a reviewer does with its task: *mode* is the task plan's, or "" for none."""
    return {"new": _KEEP, "task": _HAND_BACK}.get(mode, "")


def _tell(parent_id: str, author: str) -> str:
    return " and ".join(f"`lemonaid tell {to}`" for to in dict.fromkeys([parent_id, author]) if to)


def render(
    body: str,
    title: str,
    lemon_id: str,
    parent: tuple[str, str],
    today: datetime.date,
    values: abc.Mapping[str, str],
    area: str = "",
    output_doc: str = "",
    created: str = "",
) -> str:
    """The whole brief: lemonaid's header, then *body* filled in. *parent* is (Lemon-ID, tmux session)."""
    parent_id, parent_session = parent
    filled = {
        "title": title,
        "date": today.isoformat(),
        "lemon_id": lemon_id,
        "wordybin": identity.brief_name(lemon_id) or lemon_id,
        "relay_name": signature.spaced(identity.brief_name(lemon_id) or lemon_id),
        "parent_id": parent_id,
        "tell": _tell(parent_id, values.get("author", "")),
        **values,
    }
    try:
        text = string.Template(body).substitute(filled)
    except KeyError as missing:
        key = missing.args[0]
        flag = next((f for prefix, f in _FLAG_OF.items() if key.startswith(prefix)), "")
        raise Problem(
            f"The template uses ${key}; pass {flag}"
            if flag
            else f"The template uses unknown ${key}"
        ) from None
    except ValueError as cause:
        raise Problem(f"The template has a stray $: {cause}") from None

    where = f" ({parent_session})" if parent_session else ""
    rendered = "\n".join(
        [
            f"# {title}",
            "",
            f"Brief-ID: {lemon_id}",
            "",
            "type: Brief",
            "",
            *([created, ""] if created else []),
            f"Parent: {parent_id}{where}, {today.isoformat()}",
            "",
            *([f"Output-Doc: {output_doc}", ""] if output_doc else []),
            *([f"Area: {area}", ""] if area else []),
            text.strip(),
            "",
        ]
    )

    return doc_table.add(rendered, Path(output_doc), "Output document") if output_doc else rendered
