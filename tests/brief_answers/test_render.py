import dataclasses
import io

from lemonaid.brief import answer_archive, cli, render, target


def test_show_sidebar_and_popup_share_only_live_answers(brief, run, monkeypatch, capsys):
    run("answer", "--self", "Old question?", "Archived secret")
    run("answers", "archive", "--self", "--all")
    run("answer", "--self", "Current question?", "Visible answer")
    found = target.Target([brief], [], None, [], "")
    monkeypatch.setattr(cli, "_target", lambda *args: found)
    run("show", "--self")
    shown = capsys.readouterr().out
    assert "Visible answer" in shown
    assert "Archived secret" not in shown
    assert "1 archived" in shown
    view = render.view(found, 0, lambda *_: "")
    assert "Visible answer" in view.sections[0].body
    assert "1 archived" in view.sections[0].body
    assert "Archived secret" not in str(view)
    member = dataclasses.replace(found, lemon=target.Identity(name="worker"))
    session = dataclasses.replace(found, members=[member, member])
    assert all(
        "Visible answer" in section.body
        for section in render.view(session, 0, lambda *_: "").sections
    )


def test_archive_count_remains_visible_with_no_answers_section(brief, run):
    run("answer", "--self", "Why?", "Archived content")
    run("answers", "archive", "--self")
    run("section", "rm", "--self", "Answers")
    view = render.view(target.Target([brief], [], None, [], ""), 0, lambda *_: "")
    assert "1 archived" in view.sections[0].body
    assert "Archived content" not in str(view)


def test_answer_can_read_stdin_and_expand_prints_markdown(brief, run, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("Paragraph one.\n\n- item"))
    run("answer", "--self", "Why?", "-")
    assert "> Paragraph one.\n>\n> - item" in brief.read_text()
    run("answers", "archive", "--self")
    run("answers", "expand", "--self")
    assert "Paragraph one." in capsys.readouterr().out


def test_broken_archive_does_not_hide_the_live_answer(brief, run):
    run("answer", "--self", "Why?", "Visible answer")
    answer_archive.path_for(brief).write_text("not json")
    view = render.view(target.Target([brief], [], None, [], ""), 0, lambda *_: "")
    assert "Visible answer" in view.sections[0].body
    assert "could not be read" in view.sections[0].body
