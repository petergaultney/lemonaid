from pathlib import Path

from lemonaid.watch import doc_signature

_BRIEF = "# Task\n\nBrief-ID: FilmyBoy.task\n\n## Goal\n\nWork.\n"


def test_a_doc_the_brief_watches_signs_with_that_watchs_name(tmp_path: Path):
    doc = tmp_path / "review.md"
    brief = (
        _BRIEF
        + f"\n## Watching\n\n- `lemonaid watch doc --wait {doc} --me 'Filmy Boy (Reviewer)'`\n"
    )

    assert doc_signature.for_doc(brief, doc, tmp_path, ()) == "Filmy Boy (Reviewer)"


def test_any_other_doc_signs_as_the_briefs_author(tmp_path: Path):
    assert doc_signature.for_doc(_BRIEF, tmp_path / "other.md", tmp_path, ()) == "FilmyBoy (Author)"


def test_a_brief_without_an_id_has_no_signature(tmp_path: Path):
    assert doc_signature.for_doc("# Task\n", tmp_path / "other.md", tmp_path, ()) == ""
