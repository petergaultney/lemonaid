import argparse
from pathlib import Path

import pytest

from lemonaid.brief import check, doc_table, docs_cli, now_edit, sections, store, verbs_cli


def test_output_row_and_added_doc_are_watched_and_removable(tmp_path):
    output, extra = tmp_path / "output.md", tmp_path / "extra.md"
    text = f"# task\n\nOutput-Doc: {output}\n\n## Goal\n\n## Watching\n"
    assert doc_table.rows(text) == [doc_table.Row(output, "Output document")]
    text = doc_table.add(text, extra, "Read this", watch=doc_table.Watch.ALL_EDITS)
    assert check.structure(text) == []
    assert [r.path for r in doc_table.rows(text)] == [output, extra]
    assert doc_table.rows(text)[1].watch is doc_table.Watch.ALL_EDITS
    text = doc_table.remove(text, output)
    assert [r.path for r in doc_table.rows(text)] == [extra]
    assert "Output-Doc:" not in text


def test_vault_links_round_trip_and_docs_precede_done(tmp_path):
    text = "# task\n\n## Now\n\n### Done\n\n- done\n\n## Watching\n"
    path = tmp_path / "A doc.md"
    text = doc_table.add(text, path, "Explain | options", vaults=[tmp_path])
    assert "obsidian://" in text
    assert doc_table.rows(text)[0].path == path
    assert sections.find(text, "Docs").level == 2
    assert [s.heading for s in now_edit.now_of(text).sections] == ["Done"]
    assert check.structure(text) == []
    assert doc_table.add(text, path, "Updated").count(str(path)) == 1


def test_watch_modes_render_and_round_trip(tmp_path):
    for mode in doc_table.Watch:
        text = doc_table.add("# task\n", tmp_path / "design.md", "Design", watch=mode)
        assert "| Document | Purpose | Watch |" in text
        assert mode.value in text
        assert doc_table.rows(text)[0].watch is mode


def test_docs_reject_boolean_column_and_invalid_watch_mode():
    rows, problems = doc_table.parse(
        ["| Document | Purpose | Edits |", "|---|---|---|", "| /tmp/doc.md | Review | yes |"]
    )
    assert not rows and problems
    rows, problems = doc_table.parse(
        ["| Document | Purpose | Watch |", "|---|---|---|", "| /tmp/doc.md | Review | yes |"]
    )
    assert not rows and "Relay comments or All edits" in problems[0]


def test_non_vault_docs_render_file_links_and_round_trip(tmp_path):
    path = tmp_path / "a doc [draft].md"
    text = doc_table.add("# task\n", path, "Design")
    assert path.as_uri() in text
    assert doc_table.rows(text)[0].path == path


def test_doc_add_cli_uses_enum_choices():
    parser = argparse.ArgumentParser()
    docs_cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(
        ["doc", "add", "--self", "/tmp/design.md", "Design", "--watch", "All edits"]
    )
    assert args.watch is doc_table.Watch.ALL_EDITS
    args = parser.parse_args(["doc", "add", "--self", "/tmp/design.md", "Design"])
    assert args.watch is doc_table.Watch.RELAY_COMMENTS


@pytest.mark.parametrize("operation", ["add", "remove"])
@pytest.mark.parametrize("column,value", [("Edits", "yes"), ("Watch", "unexpected")])
def test_edits_refuse_an_unparsed_docs_table_without_losing_rows(operation, column, value):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    original = f"# task\n\n## Now\n\n### Docs\n\n| Document | Purpose | {column} |\n|---|---|---|\n| /tmp/first.md | First | {value} |\n| /tmp/second.md | Second | {value} |\n"
    path.write_text(original)
    change = (
        (lambda text: doc_table.add(text, path.parent / "new.md", "New"))
        if operation == "add"
        else (lambda text: doc_table.remove(text, Path("/tmp/first.md")))
    )
    error = verbs_cli.edit(path, change)
    assert "Cannot rewrite ### Docs" in error
    assert path.read_text() == original
