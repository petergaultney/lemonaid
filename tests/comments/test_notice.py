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
    real_get = db.get_by_channel

    def get_then_pause(conn, channel, unread_only=True):
        found = real_get(conn, channel, unread_only)
        if threading.current_thread().name == "seen":
            read_the_row.set()
            carry_on.wait(5)
        return found

    monkeypatch.setattr(db, "get_by_channel", get_then_pause)
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
