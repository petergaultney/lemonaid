import threading
import time

from lemonaid.messages import store
from lemonaid.watch import batch_wait, delivery


def eventually(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.01)


def start(tmp_path, text, deliver, notes=None):
    path = tmp_path / "brief.md"
    path.write_text(text)
    inbox = store.inbox_for_id("task.IndexElf")
    inbox.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "cursors"
    stop = threading.Event()
    errors = []

    def run():
        try:
            batch_wait.wait(
                path,
                inbox,
                root,
                "",
                deliver,
                lambda: not stop.is_set(),
                interval=0.01,
                quiet=0.05,
                notes=lambda: notes or {},
            )
        except delivery.Failed as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    return path, inbox, root, stop, thread, errors


BRIEF = "# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n"
