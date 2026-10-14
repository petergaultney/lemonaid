import threading

from lemonaid.messages import store
from lemonaid.watch import batch_wait

from . import shared


def test_editing_brief_adds_a_subscription_without_restarting(tmp_path):
    file = tmp_path / "later"
    file.write_text("before")
    sent = []
    path, _inbox, root, stop, thread, errors = shared.start(tmp_path, shared.BRIEF, sent.append)
    try:
        shared.eventually(lambda: (root / "briefs").exists())
        path.write_text(
            shared.BRIEF + f"- `lemonaid watch file --wait {file} --interval .01 --quiet 0`\n"
        )
        shared.eventually(lambda: bool(list((root / "file").glob("*.json"))))
        assert sent == []
        file.write_text("after")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and str(file) in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_a_half_edited_brief_reports_once_and_keeps_previous_watches(tmp_path):
    file = tmp_path / "source"
    file.write_text("before")
    text = shared.BRIEF + f"- `lemonaid watch file --wait {file} --interval .01 --quiet 0`\n"
    sent = []
    path, inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: bool(list((root / "file").glob("*.json"))))
        path.write_text(text + "- `lemonaid watch file --unknown`\n")
        file.write_text("after")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "Invalid subscriptions" in sent[0] and str(file) in sent[0]
        # Rearming an unchanged invalid brief continues the last valid subscription,
        # without repeating the already delivered diagnostic.
        later = []
        timer = threading.Timer(
            0.15, lambda: store.send(inbox, "still listening", "other.IndexElf")
        )
        timer.start()
        batch_wait.wait(
            path, inbox, root, "", later.append, lambda: True, interval=0.01, quiet=0.02
        )
        timer.join()
        assert len(later) == 1 and "still listening" in later[0]
        assert "Invalid subscriptions" not in later[0]
    finally:
        stop.set()
        thread.join(5)


def test_first_wait_with_a_bad_line_still_watches_its_valid_file(tmp_path):
    file = tmp_path / "source"
    file.write_text("before")
    text = (
        shared.BRIEF
        + f"- `sh custom.sh`\n- `lemonaid watch file --wait {file} --interval .01 --quiet 0`\n"
    )
    sent = []
    _path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, sent.append)
    try:
        shared.eventually(lambda: bool(list((root / "file").glob("*.json"))))
        file.write_text("after")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "custom.sh" in sent[0]
        later = []
        _path, _inbox, root, stop, thread, errors = shared.start(tmp_path, text, later.append)
        shared.eventually(lambda: bool(list((root / "file").glob("*.json"))))
        file.write_text("changed again")
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(later) == 1 and str(file) in later[0] and "custom.sh" not in later[0]
    finally:
        stop.set()
        thread.join(5)
