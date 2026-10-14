import time

from lemonaid.brief import doc_table
from lemonaid.messages import store
from lemonaid.watch import batch_wait, delivery

from . import shared


def test_inbox_and_two_changed_files_arrive_in_one_batch(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.write_text("before")
    two.write_text("before")
    text = (
        shared.BRIEF
        + f"- `lemonaid watch file --wait {one} --interval .01 --quiet 0`\n- `lemonaid watch file --wait {two} --interval .01 --quiet 0`\n"
    )
    sent = []
    _path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: len(list((root / "file").glob("*.json"))) == 2)
        assert sent == []
        one.write_text("after")
        two.write_text("after")
        store.send(inbox, "Please read both", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive()
        assert len(sent) == 1 and not errors
        assert str(one) in sent[0] and str(two) in sent[0] and "Please read both" in sent[0]
        assert store.pending_count(inbox) == 0
    finally:
        stop.set()
        thread.join(5)


def test_failed_delivery_keeps_file_cursor_and_inbox_pending(tmp_path):
    file = tmp_path / "source"
    file.write_text("before")
    text = shared.BRIEF + f"- `lemonaid watch file --wait {file} --interval .01 --quiet 0`\n"

    def fail(message):
        raise delivery.Failed("queue refused")

    path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, fail)
    try:
        shared.eventually(lambda: bool(list((root / "file").glob("*.json"))))
        cursor = next((root / "file").glob("*.json"))
        before = cursor.read_text()
        file.write_text("after")
        store.send(inbox, "Still pending", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive() and errors
        assert store.pending_count(inbox) == 1
        assert cursor.read_text() == before
        sent = []
        batch_wait.wait(path, inbox, root, "", sent.append, lambda: True, interval=0.01, quiet=0.01)
        assert len(sent) == 1 and str(file) in sent[0] and "Still pending" in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_doc_burst_lists_every_thread_even_when_done(tmp_path):
    doc = tmp_path / "review.md"
    doc.write_text("body\n")
    text = doc_table.add(
        shared.BRIEF.replace("Brief-ID:", "Status: done\n\nBrief-ID:"), doc, "Review"
    )
    text += (
        f'- `lemonaid watch doc --wait {doc} --quiet .08 --interval .01 --me "Author (IndexElf)"`\n'
    )
    sent = []
    _path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: (root / "doc").exists())
        for index in range(5):
            doc.write_text(
                doc.read_text() + f'\n{{{{authorId="human" author="Human">>question {index}<<}}}}\n'
            )
            time.sleep(0.02)
            assert sent == []
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1
        assert all(f"question {index}" in sent[0] for index in range(5))
    finally:
        stop.set()
        thread.join(5)


def test_a_doc_burst_continues_while_its_event_waits_for_batch_delivery(tmp_path):
    doc = tmp_path / "review.md"
    doc.write_text("body\n")
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet .02 --interval .01`\n"
    sent = []
    _path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: (root / "doc").exists())
        doc.write_text(doc.read_text() + '\n{{authorId="human" author="Human">>first<<}}\n')
        # The scout waits for the batch acknowledgement after the doc settles.
        time.sleep(0.04)
        assert sent == []
        doc.write_text(doc.read_text() + '\n{{authorId="human" author="Human">>second<<}}\n')
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "first" in sent[0] and "second" in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_a_settling_doc_does_not_delay_inbox_delivery(tmp_path):
    doc = tmp_path / "writing.md"
    doc.write_text("body\n")
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet 2 --interval .01`\n"
    sent = []
    _path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: (root / "doc").exists())
        doc.write_text(doc.read_text() + '\n{{authorId="human" author="Human">>draft<<}}\n')
        store.send(inbox, "urgent message", "other.IndexElf")
        thread.join(0.5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "urgent message" in sent[0]
        assert "draft" not in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_deleting_a_doc_with_a_pending_event_does_not_stop_inbox_delivery(tmp_path):
    doc = tmp_path / "deleted.md"
    doc.write_text('{{authorId="human" author="Human">>question<<}}')
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet 0 --interval .01`\n"
    sent = []
    _path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: (root / "doc").exists())
        time.sleep(0.01)
        doc.unlink()
        store.send(inbox, "still here", "other.IndexElf")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "still here" in sent[0]
    finally:
        stop.set()
        thread.join(5)
