"""A Codex lemon's scout, in the scout host, opens its PO box and queues the mail it gets."""

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.po_box import cards, inbox
from lemonaid.watch import codex_scout, delivery
from tests.scout_host import shared as hosted
from tests.wait import shared as waiting

from . import shared


def test_a_codex_lemon_gets_po_box_mail_through_its_scout(monkeypatch, tmp_path):
    root = shared.configure_po_box(monkeypatch, tmp_path)
    path = brief_store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\nPO box: yes\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)
    queued, alive = [], [True]
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    monkeypatch.setattr(codex_scout, "_ALIVE_EVERY", 0)
    monkeypatch.setattr(codex_scout, "thread_alive", lambda thread, max_age=0.0: alive[0])
    monkeypatch.setattr(
        delivery, "to_codex", lambda thread, kind, instruction: lambda m: queued.append(m)
    )

    with hosted.hosting():
        running = hosted.start("task.IndexElf", "codex:test", "test")
        waiting.eventually(lambda: cards.registered(root, "sam", "task.IndexElf") is not None)
        inbox.send(
            cards.registered(root, "sam", "task.IndexElf"), "From afar", "kim: other.AuditInk"
        )
        waiting.eventually(lambda: bool(queued))
        alive[0] = False
        running.stop.set()
        running.join()

    assert inbox.LABEL in queued[0] and "From afar" in queued[0]
