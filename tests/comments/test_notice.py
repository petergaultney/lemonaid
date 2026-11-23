import threading
import time

from lemonaid.comments import notice
from lemonaid.inbox import db


def test_a_reply_posted_while_another_is_acknowledged_stays_unread(tmp_path, monkeypatch) -> None:
    """Without one transaction, the acknowledgement reads the row, the reply adds its id, and
    the acknowledgement then marks the row read with the reply's id in it."""
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")
    notice.replied(path, "A (Author)", "First", "one")
    read_the_row, carry_on = threading.Event(), threading.Event()
    real_rows = notice._unread_rows

    def rows_then_pause(conn, path):
        found = real_rows(conn, path)
        if threading.current_thread().name == "seen":
            read_the_row.set()
            carry_on.wait(5)
        return found

    monkeypatch.setattr(notice, "_unread_rows", rows_then_pause)
    seeing = threading.Thread(target=notice.seen, args=(path, ["First"]), name="seen")
    seeing.start()
    read_the_row.wait(5)
    replying = threading.Thread(target=notice.replied, args=(path, "A (Author)", "Second", "two"))
    replying.start()
    time.sleep(0.3)
    carry_on.set()

    seeing.join(10)
    replying.join(10)

    assert notice.unread_ids(path) == ["Second"]


def test_each_lemon_has_its_own_row_for_a_file_and_the_file_counts_them_all(tmp_path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n")
    notice.replied(path, "A (Author)", "FromA", "one", lemon="claude:a")
    notice.replied(path, "B (Author)", "FromB", "two", lemon="claude:b")

    both = notice.unread_ids(path)
    notice.seen(path, ["FromA"])

    with db.connect() as conn:
        a_row = db.get_by_channel(conn, notice.channel(path, "claude:a"))
        b_row = db.get_by_channel(conn, notice.channel(path, "claude:b"))
    assert sorted(both) == ["FromA", "FromB"]
    assert a_row is None
    assert b_row is not None and notice.lemon_of(b_row) == "claude:b"
    assert notice.unread_ids(path) == ["FromB"]


def test_a_row_written_before_rows_named_their_lemon_still_counts(tmp_path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# A\n")
    notice.replied(path, "A (Author)", "Older", "one")
    notice.replied(path, "A (Author)", "Newer", "two", lemon="claude:a")

    found = notice.unread_ids(path)
    notice.seen(path, ["Older", "Newer"])

    assert found == ["Older", "Newer"]
    assert notice.unread_ids(path) == []


def test_reading_a_reply_leaves_another_file_s_row_alone(tmp_path) -> None:
    """Ids are unique within a file only, and a path may contain the channel's separator."""
    first, second = tmp_path / "a.md", tmp_path / "a.md|draft.md"
    first.write_text("# A\n")
    second.write_text("# B\n")
    notice.replied(first, "A (Author)", "SameId", "one", lemon="claude:a")
    notice.replied(second, "A (Author)", "SameId", "two", lemon="claude:a")

    notice.seen(first, ["SameId"])

    assert notice.unread_ids(first) == []
    assert notice.unread_ids(second) == ["SameId"]


def test_the_label_names_the_file_and_counts_its_unread_replies(tmp_path) -> None:
    path = tmp_path / "guide.md"
    path.write_text("# G\n")
    notice.replied(path, "A (Author)", "One", "one", lemon="claude:a")
    notice.replied(path, "A (Author)", "Two", "two", lemon="claude:a")
    with db.connect() as conn:
        unread = db.get_by_channel(conn, notice.channel(path, "claude:a"))
    notice.seen(path, ["One", "Two"])
    with db.connect() as conn:
        read = db.get_by_channel(conn, notice.channel(path, "claude:a"), unread_only=False)

    assert notice.label(unread) == "↳ 💬 guide.md · 2 unread"
    assert notice.label(read) == "↳ 💬 guide.md"


def _commented(comment_id: str) -> str:
    from lemonaid.comments import edits

    text = "Review this.\n"
    added = edits.add_comment(
        text,
        "markdown",
        0,
        6,
        author="a",
        body="b",
        at="2026-11-23T10:00:00Z",
        comment_id=comment_id,
    )
    return edits.apply(text, added.edits)


def test_a_removed_comment_leaves_its_row_and_a_row_left_empty_is_read(tmp_path) -> None:
    path = tmp_path / "a.md"
    notice.replied(path, "A (Author)", "Stripped", "one")

    notice.removed(path, {"Stripped"}, "Review this.\n", "markdown")

    assert notice.unread_ids(path) == []


def test_a_comment_the_file_never_held_keeps_its_row(tmp_path) -> None:
    """A comment written to another editor's unsaved buffer, or added after the strip, was
    never in the text the strip started from."""
    path = tmp_path / "a.md"
    notice.replied(path, "A (Author)", "Stripped", "one")
    notice.replied(path, "A (Author)", "Elsewhere", "two")

    notice.removed(path, {"Stripped"}, "Review this.\n", "markdown")

    assert notice.unread_ids(path) == ["Elsewhere"]


def test_a_comment_whose_record_can_t_be_read_isn_t_taken_for_removed(tmp_path) -> None:
    path = tmp_path / "a.md"
    notice.replied(path, "A (Author)", "Broken", "one")
    after = _commented("Broken").replace('"body": "b"', '"body": b')

    notice.removed(path, {"Broken"}, after, "markdown")

    assert notice.unread_ids(path) == ["Broken"]
