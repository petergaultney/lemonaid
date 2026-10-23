"""The maintainer's name appears in no tracked text file except where it must.

_ALLOWED may only shrink: a stale entry fails too.
"""

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parent.parent

_NAME = re.compile("|".join(("pe" + "ter", "gault" + "ney")), re.IGNORECASE)
_OWNER = "pe" + "tergault" + "ney"
_RESPONSIBLE_PARTY = "Pe" + "ter Gault" + "ney"
_OWNER_URL = re.compile(
    rf"(?:github\.com|githubusercontent\.com)/{_OWNER}/|(?<![\w/.~-]){_OWNER}/lemonaid\b"
)

_FROZEN = "CHANGES.md"  # history up to 0.115.3

_ALLOWED: dict[str, tuple[int, str]] = {
    "LICENSE": (1, "the copyright line"),
}


def _hits(text: str) -> list[int]:
    """Line numbers naming the maintainer outside URLs and required document ownership."""
    hits = []
    frontmatter = text.startswith("---\n")
    responsible = False
    for number, line in enumerate(text.splitlines(), 1):
        if number > 1 and line == "---":
            frontmatter = False
        if responsible and line == f"  - {_RESPONSIBLE_PARTY}":
            responsible = False
            continue
        responsible = frontmatter and line == "responsible-parties:"
        if _NAME.search(_OWNER_URL.sub("", line)):
            hits.append(number)
    return hits


def _tracked_text() -> list[tuple[str, str]]:
    names = (
        subprocess.run(["git", "ls-files", "-z"], cwd=_ROOT, capture_output=True, check=True)
        .stdout.decode()
        .split("\0")
    )
    found: list[tuple[str, str]] = []
    for name in filter(None, names):
        try:
            found.append((name, (_ROOT / name).read_text()))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, deleted in the worktree, or a submodule

    return found


def test_hits_ignores_the_github_owner_and_reports_line_numbers():
    name = "Pe" + "ter"
    text = (
        f"https://github.com/{_OWNER}/lemonaid\nfine\nNeeds {name}\n"
        f"[pr: {_OWNER}/lemonaid, 1], {name}\n"
    )

    assert _hits(text) == [3, 4]


def test_hits_does_not_exempt_a_home_directory():
    assert _hits(f"/Users/{_OWNER}/x\n~/{_OWNER}/lemonaid\n") == [1, 2]


def test_hits_matches_case_insensitively():
    assert _hits("GAULT" + "NEY\n") == [1]


def test_required_frontmatter_owner_does_not_exempt_other_fields_or_body():
    text = (
        f"---\nresponsible-parties:\n  - {_RESPONSIBLE_PARTY}\n"
        f"created-by: {_RESPONSIBLE_PARTY}\n---\nNeeds {_RESPONSIBLE_PARTY}\n"
    )
    assert _hits(text) == [4, 6]


def test_owner_exception_requires_initial_frontmatter_and_first_list_entry():
    assert _hits(f"# Body\nresponsible-parties:\n  - {_RESPONSIBLE_PARTY}\n") == [3]
    assert _hits(
        f"---\nresponsible-parties:\n  - Someone Else\n  - {_RESPONSIBLE_PARTY}\n---\n"
    ) == [4]


def _hit_counts() -> dict[str, int]:
    return {
        name: len(_hits(text)) for name, text in _tracked_text() if name != _FROZEN and _hits(text)
    }


def test_no_tracked_file_names_the_maintainer_beyond_the_allow_list():
    counts = _hit_counts()
    offenders = [
        f"{name}: {count} hits, {_ALLOWED.get(name, (0, ''))[0]} allowed"
        for name, count in counts.items()
        if count != _ALLOWED.get(name, (0, ""))[0]
    ]

    assert offenders == []


def test_allow_list_has_no_stale_entries():
    assert sorted(set(_ALLOWED) - set(_hit_counts())) == []
