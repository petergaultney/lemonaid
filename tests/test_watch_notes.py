import pathlib

from lemonaid.watch import kinds, notes


def test_load_renders_each_harness_section_for_its_own_harness(tmp_path):
    (tmp_path / "child.done.md").write_text(
        "Toss it.\n<!-- harness: codex -->\nThen rearm.\n<!-- /harness -->\n"
    )
    assert notes.load(tmp_path, "claude").notes == {"child.done": "Toss it."}
    assert notes.load(tmp_path, "codex").notes == {"child.done": "Toss it.\nThen rearm."}


def test_load_reports_a_file_that_names_no_kind_and_skips_it(tmp_path):
    (tmp_path / "child.finished.md").write_text("x")
    loaded = notes.load(tmp_path, "claude")
    assert loaded.notes == {}
    assert len(loaded.problems) == 1 and "child.finished" in loaded.problems[0]


def test_load_cuts_a_long_note_and_says_so(tmp_path):
    (tmp_path / "child.done.md").write_text("x" * (notes.MAX_CHARS + 50))
    loaded = notes.load(tmp_path, "claude")
    assert len(loaded.notes["child.done"]) == notes.MAX_CHARS + 4
    assert loaded.problems


def test_load_reports_an_unknown_harness_marker_and_skips_the_note(tmp_path):
    (tmp_path / "child.done.md").write_text("<!-- harness: emacs -->\nx\n<!-- /harness -->\n")
    loaded = notes.load(tmp_path, "claude")
    assert loaded.notes == {} and "emacs" in loaded.problems[0]


def test_load_reports_an_undecodable_note_and_skips_it(tmp_path):
    (tmp_path / "child.done.md").write_bytes(b"\xff\xfe\xfa")
    loaded = notes.load(tmp_path, "claude")
    assert loaded.notes == {} and "cannot read" in loaded.problems[0]


def test_load_without_a_notes_directory_is_empty(tmp_path):
    assert notes.load(tmp_path / "missing", "claude") == notes.Loaded({}, [])


def test_appendix_lists_each_noted_kind_once_and_indents_continuation_lines():
    text = notes.appendix(
        ["child.done", "child.merge", "child.done"], {"child.done": "Toss it.\nOr say why."}
    )
    assert text == "Your notes for these events:\n- child.done: Toss it.\n  Or say why."


def test_appendix_is_empty_when_no_kind_has_a_note():
    assert notes.appendix(["child.done"], {}) == ""


def test_every_origin_has_a_kind_for_each_status_and_problem():
    assert {"child.done", "watched.done", "orphan.none", "child.needs", "child.deaf"} <= set(
        kinds.KINDS
    )


def test_the_docs_name_every_origin_and_event_of_every_kind():
    docs = (pathlib.Path(__file__).parents[1] / "docs" / "event-notes.md").read_text()
    for kind in kinds.KINDS:
        origin, event = kind.split(".")
        assert f"`{origin}`" in docs and f"`{event}`" in docs, kind
