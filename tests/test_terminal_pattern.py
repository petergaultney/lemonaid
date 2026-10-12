"""The terminal regex finds a vault path as printed, spaces and all."""

import re
from pathlib import Path

import pytest

from lemonaid.terminal import iterm2_rules, pattern

_REGEX = re.compile(pattern.vault_path_regex([Path.home() / "trove", Path("/srv/notes (old)")]))


@pytest.mark.parametrize(
    ("line", "found"),
    [
        (
            "see ~/trove/94 System Lemons/rules-of-the-grove.md.",
            ["~/trove/94 System Lemons/rules-of-the-grove.md"],
        ),
        (f"at {Path.home()}/trove/a b/c.md, then", [f"{Path.home()}/trove/a b/c.md"]),
        ("~/trove/a.md and ~/trove/b c.md", ["~/trove/a.md", "~/trove/b c.md"]),
        ("/srv/notes (old)/x.md", ["/srv/notes (old)/x.md"]),
        ("~/trove/a.mdx", []),
        ("~/trove/script.py", []),
        ("~/elsewhere/a.md", []),
        ("`~/trove/a` b.md", [" b.md"]),
    ],
)
def test_vault_paths_match_with_spaces(line, found):
    assert _REGEX.findall(line) == found


def test_no_backslash_escapes_a_character_rust_regex_rejects():
    assert pattern.vault_path_regex([Path("/a~b/x-y z")]).startswith(r"(?:/a~b/x-y z)/")


@pytest.mark.parametrize(
    "line",
    ["~/trove/x;touch y;.md", "~/trove/a $(rm -r ~).md", "~/trove/a `id`.md", "~/trove/a & b.md"],
)
def test_a_match_never_contains_an_excluded_character(line):
    regex = pattern.vault_path_regex([Path.home() / "trove"], iterm2_rules.SHELL_CHARS)

    assert not [m for m in re.findall(regex, line) if any(c in m for c in iterm2_rules.SHELL_CHARS)]


_RELATIVE = re.compile(
    pattern.vault_path_regex([Path.home() / "trove"], spaced_folders=["94 System Lemons"])
)


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("see product-dev/pitches/c.md.", ["product-dev/pitches/c.md"]),
        ("read 94 System Lemons/rules.md now", ["94 System Lemons/rules.md"]),
        ("open top-of-mind.md", ["top-of-mind.md"]),
        ("a/b.md and c/d.md", ["a/b.md", "c/d.md"]),
        ("src/foo.py", []),
        ('(docs/a.md) and "b/c.md"', []),
        ("see https://github.com/o/r/blob/main/README.md", []),
        ("notes.mdx", []),
        ("edit /Users/p/repo/docs/a.md", []),
        ("edit ~/repo/a.md ./b.md ../c.md", []),
        ("src/my-README.md", ["src/my-README.md"]),
        ("~/trove/a.md", ["~/trove/a.md"]),
    ],
)
def test_relative_paths_match_wherever_a_token_starts(line, found):
    assert [m.strip() for m in _RELATIVE.findall(line)] == found
