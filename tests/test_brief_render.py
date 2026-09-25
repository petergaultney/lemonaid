"""What a brief shows first: who, its status, and what it needs from Peter."""

from pathlib import Path

from lemonaid.brief import render, target

_AUTHOR = target.Identity("author", "", "Claude", "Opus", "work", "2", "~/work", "feat/x", "")
_REVIEWER = target.Identity("reviewer", "", "Codex", "", "work", "4", "~/work", "feat/x", "")


def _brief(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / f"{name}.md"
    path.write_text(text)
    return path


def _no_prs(ref: str, cwd: Path | None) -> str:
    return ""


def test_needs_peter_comes_right_after_identity_and_status_whatever_the_order(tmp_path):
    path = _brief(
        tmp_path,
        "task",
        "# Task\n\nStatus: blocked\n\n## Now\n- Done: a lot\n- Next: more\n"
        "- Waiting on: nothing\n- Needs Peter: say yes\n",
    )

    out = render.markdown(target.Target([path], [], None, [], "", lemon=_AUTHOR), 0, _no_prs)

    assert out.startswith("### author · Claude / Opus · work:2\n\n**Status:** blocked\n\n")
    assert "> **Needs Peter:** say yes" in out
    assert out.index("Needs Peter") < out.index("**Task**") < out.index("**Next:**")
    assert out.index("**Next:** more") < out.index("**Done:** a lot")
    assert "Waiting on" not in out


def test_sub_headings_render_like_bullets(tmp_path):
    path = _brief(
        tmp_path,
        "task",
        "# Task\n\nStatus: blocked\n\n## Now\n### Done\n- a\n\n### Needs Peter\n- one\n- two\n",
    )

    out = render.markdown(target.Target([path], [], None, [], "", lemon=_AUTHOR), 0, _no_prs)

    assert "> **Needs Peter:**\n>\n> - one\n> - two" in out
    assert out.index("> - two") < out.index("**Done:**")


def test_pr_state_follows_the_status(tmp_path):
    path = _brief(tmp_path, "task", "# Task\n\nStatus: waiting\n\n## Now\n- Waiting on: PR #74\n")
    asked: list[tuple[str, Path | None]] = []

    def pr_state(ref: str, cwd: Path | None) -> str:
        asked.append((ref, cwd))
        return "merged"

    out = render.markdown(target.Target([path], [], None, [], "", lemon=_AUTHOR), 0, pr_state)

    assert "**Status:** waiting  \n**PR:** #74 merged" in out
    assert asked == [("74", tmp_path)]


def test_a_session_shows_window_two_in_full_and_the_rest_compact(tmp_path):
    author = _brief(tmp_path, "a", "# Build\n\nStatus: working\n\n## Now\n- Next: tests\n")
    reviewer = _brief(
        tmp_path,
        "r",
        "# Review\n\nStatus: waiting\n\n## Now\n- Done: pass one\n- Next: pass two\n"
        "- Waiting on:\n  - fixes\n  - CI\n- Needs Peter: a ruling\n",
    )
    found = target.Target(
        [reviewer, author],
        [],
        None,
        [],
        "work",
        "# work · 2 lemons",
        identities={author: _AUTHOR, reviewer: _REVIEWER},
    )

    out = render.markdown(found, 0, _no_prs)

    assert out.startswith("# work · 2 lemons\n\n---\n\n### w2 · author · Claude / Opus")
    reviewer_part = out[out.index("### w4 · reviewer · Codex") :]
    assert "> **Needs Peter:** a ruling" in reviewer_part
    assert "**Waiting on:** fixes (+1 more)" in reviewer_part
    assert "pass one" not in out and "pass two" not in out
    assert "**Next:** tests" in out
    assert out.count("~/work · feat/x") == 1
