"""scripts/changefiles.py: parsing change files and the version and notes they make."""

import pytest

from .shared import changefiles

_PATCH = "# Patch\n\n- **A fix.**\n"
_MINOR = "# Minor\n\n- **A feature.**\n"
_MAJOR = "# Major\n\n- **A break.**\n"


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("2026-10-14-fix-the-thing.md", True),
        ("2026-10-14-a-b-c-d-e-f.md", True),
        ("2026-10-14-fix.md", False),
        ("2026-10-14-a-b-c-d-e-f-g.md", False),
        ("2026-10-14-Fix-Thing.md", False),
        ("0.116.0-fix-the-thing.md", False),
        ("README.md", False),
    ],
)
def test_names_are_a_date_and_a_two_to_six_word_title(name: str, ok: bool):
    assert changefiles.is_change_file_name(name) is ok


def test_parse_reads_the_bump_heading_and_the_entry():
    assert changefiles.parse("2026-10-14-new-feature.md", _MINOR) == (
        changefiles.Bump.MINOR,
        "- **A feature.**\n",
    )


@pytest.mark.parametrize(
    "text", ["- no heading\n", "# Minor\n\n", "# 0.116.0\n\n- versioned\n", "\n# Patch\n- late\n"]
)
def test_parse_rejects_a_malformed_file(text: str):
    with pytest.raises(changefiles.MalformedChange):
        changefiles.parse("2026-10-14-new-feature.md", text)


def test_latest_version_takes_the_highest_tag_numerically():
    assert changefiles.latest_version(["v0.9.0", "v0.115.3", "v0.115.10", "junk"]) == "0.115.10"


def test_next_version_takes_the_highest_bump_among_mixed_files():
    changes = {
        "2026-10-12-small-fix.md": _PATCH,
        "2026-10-14-new-feature.md": _MINOR,
        "2026-10-13-other-fix.md": _PATCH,
    }
    assert changefiles.next_version(changes, "v0.115.3") == "0.116.0"


@pytest.mark.parametrize(
    ("bump", "version"), [(_PATCH, "0.115.4"), (_MINOR, "0.116.0"), (_MAJOR, "1.0.0")]
)
def test_next_version_applies_each_bump(bump: str, version: str):
    assert changefiles.next_version({"2026-10-14-one-change.md": bump}, "0.115.3") == version


def test_no_change_files_is_nothing_to_release():
    with pytest.raises(changefiles.NothingToRelease):
        changefiles.next_version({}, "0.115.3")


def test_every_malformed_file_is_named():
    changes = {"2026-10-14-bad-one.md": "- x\n", "2026-10-14-bad-two.md": "# Tiny\n- y\n"}
    with pytest.raises(changefiles.MalformedChange) as err:
        changefiles.next_version(changes, "0.115.3")
    assert "bad-one" in str(err.value)
    assert "bad-two" in str(err.value)


def test_release_notes_join_the_entries_in_date_order():
    changes = {"2026-10-14-new-feature.md": _MINOR, "2026-10-12-small-fix.md": _PATCH}
    assert changefiles.release_notes(changes) == "- **A fix.**\n\n- **A feature.**\n"


def test_release_notes_group_repeated_sections_in_stable_order():
    changes = {
        "2026-10-14-later-fix.md": "# Patch\n\n#### Fixed\n\n- Later fix.\n",
        "2026-10-12-first-fix.md": (
            "# Minor\n\n#### Fixed\n\n- First fix.\n  More detail.\n\n"
            "#### Added\n\n- New feature.\n\n#### Changed\n\n- New behavior.\n"
        ),
    }
    assert changefiles.release_notes(changes) == (
        "#### Added\n\n- New feature.\n\n#### Changed\n\n- New behavior.\n\n"
        "#### Fixed\n\n- First fix.\n  More detail.\n\n- Later fix.\n"
    )


def test_release_notes_preserve_unheaded_entries_and_other_sections():
    changes = {
        "2026-10-12-small-fix.md": (
            "# Patch\n\nIntro.\n\n#### Custom\n\n- Custom entry.\n\n"
            "#### Security\n\n- Security entry.\n"
        ),
        "2026-10-14-later-fix.md": "# Patch\n\n#### Custom\n\n- Another entry.\n",
    }
    assert changefiles.release_notes(changes) == (
        "Intro.\n\n#### Security\n\n- Security entry.\n\n"
        "#### Custom\n\n- Custom entry.\n\n- Another entry.\n"
    )


def test_pyproject_version_reads_only_the_top_level_line():
    assert changefiles.pyproject_version('[project]\nversion = "0.115.3"\n') == "0.115.3"
    assert changefiles.pyproject_version('[project]\ndynamic = ["version"]\n') is None
