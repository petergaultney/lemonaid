import json

import pytest

from lemonaid.brief import answer_archive, check, sections, store


def test_archive_top_then_all_and_expand_without_restoring(brief, run, capsys):
    run("answer", "--self", "First?", "Older answer")
    run("answer", "--self", "Second?", "Newer answer")
    run("answers", "archive", "--self", "1", "--json")
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["archived"] == 1
    assert "Newer answer" not in brief.read_text()
    assert "Older answer" in brief.read_text()
    run("answers", "expand", "--self", "--json")
    assert "Newer answer" in json.loads(capsys.readouterr().out)["answers"][0]
    assert "Newer answer" not in brief.read_text()
    run("answers", "archive", "--self", "--all")
    assert len(answer_archive.read(brief)) == 2
    assert "answer" not in "\n".join(
        sections.body(brief.read_text(), sections.find(brief.read_text(), "Answers"))
    )
    assert check.structure(brief.read_text()) == []
    run("answers", "archive", "--self", "--all")
    assert len(answer_archive.read(brief)) == 2


@pytest.mark.parametrize("args", [("0",), ("-1",), ("2", "--all")])
def test_invalid_archive_arguments_do_not_change_files(brief, run, args):
    run("answer", "--self", "Why?", "Answer")
    before = brief.read_text()
    with pytest.raises(SystemExit):
        run("answers", "archive", "--self", *args)
    assert brief.read_text() == before
    assert not answer_archive.path_for(brief).exists()


def test_archive_write_failure_preserves_live_answers(brief, run, monkeypatch):
    run("answer", "--self", "Why?", "Keep this answer")
    before = brief.read_text()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(answer_archive, "save", fail)
    with pytest.raises(SystemExit):
        run("answers", "archive", "--self")
    assert brief.read_text() == before


def test_interrupted_removal_is_safe_to_retry(brief, run, monkeypatch):
    run("answer", "--self", "Why?", "Keep this answer")
    replace = store._replace

    def fail(path, text):
        if path == brief:
            raise OSError("brief could not be replaced")
        replace(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_replace", fail)
        with pytest.raises(SystemExit):
            run("answers", "archive", "--self")
    assert "Keep this answer" in brief.read_text()
    run("answers", "archive", "--self")
    assert len(answer_archive.read(brief)) == 1
    assert "Keep this answer" not in brief.read_text()


def test_corrupt_archive_is_not_overwritten(brief, run):
    run("answer", "--self", "Why?", "Keep this answer")
    before = brief.read_text()
    answer_archive.path_for(brief).write_text('{"wrong": []}')
    with pytest.raises(SystemExit):
        run("answers", "archive", "--self")
    assert brief.read_text() == before
    assert answer_archive.path_for(brief).read_text() == '{"wrong": []}'


def test_archive_symlink_outside_briefs_is_refused(brief, run, tmp_path):
    run("answer", "--self", "Why?", "Keep this answer")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("[]")
    answer_archive.path_for(brief).symlink_to(outside)
    with pytest.raises(SystemExit):
        run("answers", "archive", "--self")
    assert outside.read_text() == "[]"
    assert "Keep this answer" in brief.read_text()
