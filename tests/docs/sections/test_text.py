from lemonaid.docs import sections

_DOC = """---
package: author
---
# PRs

Intro.

## Draft and ready

Open as a draft.

```sh
# not a heading
gh pr create --draft
```

### Marking ready

After review.

## Merging

A maintainer merges.
"""


def test_the_whole_doc_has_no_frontmatter():
    assert sections.text(_DOC).startswith("# PRs\n")


def test_a_section_runs_to_the_next_heading_at_its_level_and_skips_fenced_code():
    assert sections.text(_DOC, "draft and ready") == "\n".join(
        [
            "## Draft and ready",
            "",
            "Open as a draft.",
            "",
            "```sh",
            "# not a heading",
            "gh pr create --draft",
            "```",
            "",
            "### Marking ready",
            "",
            "After review.",
        ]
    )


def test_a_missing_section_is_empty():
    assert sections.text(_DOC, "Releasing") == ""
