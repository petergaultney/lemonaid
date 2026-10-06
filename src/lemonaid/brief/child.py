"""Child briefs: a dated brief for a lemon not started yet, from a template.

A template is the body of a brief, from `## Goal` down, with `$name` placeholders
(Python's `string.Template`; `$$` is a literal `$`). Lemonaid writes the header
above it: the title, `Brief-ID:`, `Status: working`, `Parent:`, and `Area:` when
`--area` gives one. The child writes `## Now` itself, after `Status:`.

`<lemons dir>/brief-templates/<name>.md` replaces the packaged template of that name.
"""

import datetime
import re
import shlex
import string
from collections import abc
from pathlib import Path

from .. import home
from . import links

PACKAGED_DIR = Path(__file__).parent / "templates"

_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_PR_URL = re.compile(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)/?")
_FLAG_OF = {"pr": "--pr", "review_doc": "--review-doc"}


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
    if match := _PR_URL.fullmatch(pr):
        repo, number = match.groups()
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


def review_doc_values(review_doc: str, vaults: abc.Iterable[Path]) -> dict[str, str]:
    path = Path(review_doc).expanduser().absolute()
    url = links.obsidian_url(path, vaults)
    return {
        "review_doc": str(path),
        "review_doc_arg": shlex.quote(str(path)),
        "review_doc_link": f"[{path.stem}]({url})" if url else f"`{path}`",
    }


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
) -> str:
    """The whole brief: lemonaid's header, then *body* filled in. *parent* is (Lemon-ID, tmux session)."""
    parent_id, parent_session = parent
    filled = {
        "title": title,
        "date": today.isoformat(),
        "lemon_id": lemon_id,
        "wordybin": lemon_id.rsplit(".", 1)[-1],
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
    return "\n".join(
        [
            f"# {title}",
            "",
            f"Brief-ID: {lemon_id}",
            "",
            "Status: working",
            "",
            f"Parent: {parent_id}{where}, {today.isoformat()}",
            "",
            *([f"Area: {area}", ""] if area else []),
            text.strip(),
            "",
        ]
    )
