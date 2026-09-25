"""What a brief shows first: who, its status, and what it needs from Peter."""

from pathlib import Path

from lemonaid.brief import render, target

_WHERE = {"tmux_session": "work", "directory": "~/work", "branch": "feat/x"}
_AUTHOR = target.Identity(name="author", backend="Claude", model="Opus", tmux_window="2", **_WHERE)
_REVIEWER = target.Identity(name="reviewer", backend="Codex", tmux_window="4", **_WHERE)


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


def test_every_lemon_in_a_session_gets_a_section_with_its_own_brief_or_none(tmp_path):
    author = _brief(tmp_path, "a", "# Build\n\nStatus: working\n\n## Now\n- Next: tests\n")
    notes = tmp_path / "place" / ".z"
    notes.mkdir(parents=True)
    (notes / "brief-codex.md").write_text(
        "# Review\n\nStatus: waiting\n\n## Now\n- Waiting on: CI\n"
    )
    place = tmp_path / "place"
    third = target.Identity(name="helper", backend="Claude", tmux_window="5", **_WHERE)
    found = target.Target(
        [author],
        [place],
        place,
        ["work"],
        "work",
        "# work · 3 lemons",
        members=[
            target.Target([], [place], place, ["codex"], "r", lemon=_REVIEWER),
            target.Target([author], [place], place, ["claude"], "a", lemon=_AUTHOR),
            target.Target([], [place], place, ["helper"], "h", lemon=third),
        ],
    )

    shown = render.view(found, 0, _no_prs)
    out = render.to_markdown(shown, 0)

    assert [s.lemon.name for s in shown.sections] == ["author", "reviewer", "helper"]
    assert [s.title for s in shown.sections] == ["Build", "Review", ""]
    assert out.index("### w4 · reviewer") < out.index("**Waiting on:** CI") < out.index("### w5")
    assert out.endswith("updated just now*") and out.count("updated") == 2
    assert shown.sections[2].body == "No brief is attached, and none in `.z/` is named for it."


def test_a_brief_named_for_the_session_is_shown_for_one_lemon_only(tmp_path):
    place = tmp_path / "place"
    (place / ".z").mkdir(parents=True)
    (place / ".z" / "brief-work.md").write_text("# Shared\n\nStatus: working\n")
    found = target.Target(
        [],
        [place],
        place,
        ["work"],
        "work",
        "# work · 2 lemons",
        members=[
            target.Target([], [place], place, ["codex", "work"], "r", lemon=_REVIEWER),
            target.Target([], [place], place, ["claude", "work"], "a", lemon=_AUTHOR),
        ],
    )

    shown = render.view(found, 0, _no_prs)

    assert [s.path for s in shown.sections] == [place / ".z" / "brief-work.md", None]
    assert shown.sections[1].body == (
        "No brief is attached; the one in `.z/` is shown for another lemon above."
    )
