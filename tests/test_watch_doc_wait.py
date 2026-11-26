"""The doc waiter's loops, as an OpenClaw doc watch runs them."""

import time

from lemonaid.watch import doc_events, doc_wait, turns


def test_an_event_waits_out_the_lemons_turn_and_goes_once_it_ends(tmp_path):
    doc = tmp_path / "draft.md"
    doc.write_text("body\n")
    w = doc_events.open_watch(tmp_path / "state", doc, "Ada", [], edits=False, quiet=0)
    doc.write_text('body\n\n{{authorId="human" author="Human">>first<<}}\n')
    asked = []

    def latest_turn():
        asked.append(len(asked))
        if len(asked) == 3:
            doc.write_text(doc.read_text() + '\n{{authorId="human" author="Human">>second<<}}\n')
        return turns.Turn(len(asked) < 5, time.time(), 0)

    sent: list[str] = []
    doc_wait.wait_doc(w, sent.append, once=True, interval=0, latest_turn=latest_turn)

    assert len(sent) == 1 and "first" in sent[0] and "second" in sent[0]
