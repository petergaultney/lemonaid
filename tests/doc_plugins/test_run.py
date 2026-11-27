from pathlib import Path

from lemonaid.doc_plugins import run
from lemonaid.plugins import processes

from .shared import fake

_DOC = Path("notes.md")


def test_an_unchanged_text_is_answered_without_asking_the_plugin():
    plugin = fake()
    first = run.call(plugin, "body", _DOC, "prose\n%% Sam: why?\n")
    processes.close()

    assert run.call(plugin, "body", _DOC, "prose\n%% Sam: why?\n") == first
    assert processes.Launch(run._KIND, plugin) not in processes._running


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
