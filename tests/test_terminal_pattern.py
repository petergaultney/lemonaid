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
        ("`~/trove/a` b.md", []),
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
def test_excluded_characters_never_match(line):
    regex = pattern.vault_path_regex([Path.home() / "trove"], iterm2_rules.SHELL_CHARS)

    assert re.findall(regex, line) == []
