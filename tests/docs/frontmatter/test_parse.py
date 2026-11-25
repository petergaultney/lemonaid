from pathlib import Path

from lemonaid.docs import frontmatter

_PATH = Path("/docs/pr.md")


def test_frontmatter_without_a_package_or_triggers_is_not_indexed():
    assert frontmatter.parse(_PATH, {"type": "Notes", "reminder": "Be brief."}) is None


def test_a_doc_s_packages_triggers_and_reminder():
    parsed = frontmatter.parse(
        _PATH,
        {
            "package": ["author", "reviewer"],
            "load-when": [
                {"command": "^gh pr create", "section": "Draft and ready", "before": True},
                {"edit": "*.md"},
            ],
            "reminder": "  Open PRs as drafts.\n",
        },
    )

    assert parsed == frontmatter.Doc(
        path=_PATH,
        packages=("author", "reviewer"),
        triggers=(
            frontmatter.Trigger("command", "^gh pr create", "Draft and ready", before=True),
            frontmatter.Trigger("edit", "*.md"),
        ),
        reminder="Open PRs as drafts.",
    )


def test_a_bad_trigger_is_dropped_and_the_rest_kept():
    parsed = frontmatter.parse(
        _PATH,
        {
            "load-when": [
                {"command": "gh pr (create"},
                {"command": "^git push", "edit": "*.py"},
                {"sometime": "later"},
                "git commit",
                {"prompt": "(?i)merge"},
            ]
        },
    )

    assert parsed is not None
    assert parsed.triggers == (frontmatter.Trigger("prompt", "(?i)merge"),)


def test_a_package_for_item_that_is_not_a_mapping_matches_nobody():
    parsed = frontmatter.parse(_PATH, {"package-for": ["everyone"]})

    assert parsed is not None
    assert parsed.lemons == ({"not": {}},)


def test_a_trigger_keeps_the_lemon_keys_that_limit_it():
    parsed = frontmatter.parse(
        _PATH, {"load-when": [{"command": "rerun", "group": "oria", "before": True}]}
    )

    assert parsed is not None
    assert parsed.triggers == (
        frontmatter.Trigger("command", "rerun", before=True, lemon={"group": "oria"}),
    )
