from pathlib import Path

from lemonaid.stalls import doc_authors

from .shared import comment


def test_a_doc_is_read_again_only_once_it_changes(tmp_path: Path, monkeypatch) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(comment("Author (Mot)"))
    reads = []
    original = doc_authors.read
    monkeypatch.setattr(doc_authors, "read", lambda path: reads.append(path) or original(path))
    cache = doc_authors.Cache()

    assert cache.read(doc) == {"Author (Mot)"}
    assert cache.read(doc) == {"Author (Mot)"}
    assert len(reads) == 1

    doc.write_text(comment("Author (Mot)") + comment("Reviewer (Salty)"))
    assert cache.read(doc) == {"Author (Mot)", "Reviewer (Salty)"}
    assert len(reads) == 2

    doc.unlink()
    assert cache.read(doc) == frozenset()
