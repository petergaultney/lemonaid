from pathlib import Path

from lemonaid.doc_plugins import run

from .shared import fake

_DOC = Path("notes.md")


def test_an_unchanged_text_is_answered_without_asking_the_plugin():
    plugin = fake()
    first = run.call(plugin, "body", _DOC, "prose\n%% Sam: why?\n")
    run.stop_all()

    assert run.call(plugin, "body", _DOC, "prose\n%% Sam: why?\n") == first
    assert plugin not in run._running


def test_each_document_and_reader_keeps_only_its_latest_answer():
    plugin = fake()
    run._results.clear()
    for n in range(20):
        run.call(plugin, "body", _DOC, f"draft {n}\n")
        run.call(plugin, "threads", _DOC, f"draft {n}\n", ["Mo"])
    run.call(plugin, "threads", _DOC, "draft 19\n", ["Sam"])
    run.call(plugin, "body", Path("other.md"), "draft 19\n")

    assert len(run._results) == 4
    assert run.call(plugin, "body", _DOC, "draft 3\n") == "draft 3\n"
