from lemonaid.messages import store

from . import shared


def test_a_missing_doc_reaches_its_lemon_once_without_changing_the_brief(tmp_path):
    doc = tmp_path / "review.md"
    doc.write_text("body\n")
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet 0 --interval .01`\n"
    sent = []
    path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    renamed = tmp_path / "renamed.md"
    try:
        shared.eventually(lambda: bool(list((root / "doc").glob("*.presence.json"))))
        doc.rename(renamed)
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1
        assert f"[doc: {doc}]" in sent[0]
        assert "no longer present" in sent[0] and str(renamed) in sent[0]
        assert path.read_text() == text
    finally:
        stop.set()
        thread.join(5)

    later = []
    path, inbox, _root, stop, thread, errors = shared.start(tmp_path, text, later.append)
    try:
        store.send(inbox, "Other work", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(later) == 1 and "Other work" in later[0]
        assert "no longer present" not in later[0]
        assert path.read_text() == text
    finally:
        stop.set()
        thread.join(5)
