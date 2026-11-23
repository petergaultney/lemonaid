import argparse
import io
import os
import subprocess
import sys
import threading
import time

import pytest

from lemonaid.comments import cli, edits, parse


def _run(*argv: str, stdin: str = "") -> int:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["comments", *argv])
    with pytest.raises(SystemExit) as exited, pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin", io.StringIO(stdin))
        args.func(args)
    return exited.value.code


@pytest.fixture
def code(tmp_path):
    path = tmp_path / "a.py"
    path.write_bytes(b"import os\r\n\r\n\r\ndef f(x):\r\n    return x + 1\r\n")
    return path


def test_add_anchors_the_lines_and_keeps_the_file_s_line_endings(code, capsys) -> None:
    assert _run("add", str(code), "--lines", "4-5", "--as", "caleb.gregory", "why +1?") == 0

    comment_id = capsys.readouterr().out.strip()
    text = code.read_bytes().decode()
    doc = parse.parse(text, "python")
    assert [c.id for c in doc.comments] == [comment_id]
    assert text[doc.anchors[0].start : doc.anchors[0].end] == "def f(x):\r\n    return x + 1\r\n"
    assert "\n" not in text.replace("\r\n", "")


def test_reply_resolve_and_strip_give_back_the_original_file(code, capsys) -> None:
    original = code.read_bytes()
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()

    assert (
        _run("reply", str(code), "--re", root, "--as", "HillyHad (Author)", "-", stdin="because\n")
        == 0
    )
    assert _run("resolve", str(code), root, "--as", "caleb.gregory") == 0
    assert parse.parse(code.read_bytes().decode(), "python").resolutions[0].resolves == root
    assert _run("strip", str(code)) == 0
    assert code.read_bytes() == original


def test_list_unanswered_needs_a_name(code, capsys) -> None:
    assert _run("list", str(code), "--unanswered") == 2
    assert "--unanswered needs --me" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["add", "{path}", "--lines", "99", "--as", "a", "hi"],
        ["add", "{path}", "--lines", "4", "--as", "a", "  "],
        ["reply", "{path}", "--re", "Gone", "--as", "a", "hi"],
    ],
)
def test_a_refused_write_leaves_the_file_alone(code, capsys, argv) -> None:
    original = code.read_bytes()

    exit_code = _run(*(arg.format(path=code) for arg in argv))

    assert exit_code == 2
    assert capsys.readouterr().err.startswith(f"{code}: ")
    assert code.read_bytes() == original


def test_a_file_that_can_t_hold_comments_is_refused(tmp_path, capsys) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello\n")

    assert _run("list", str(path)) == 2
    assert "only in Python (.py) and Markdown (.md) files" in capsys.readouterr().err


def test_add_through_a_symlink_changes_the_file_and_keeps_the_link(code, tmp_path, capsys) -> None:
    alias = tmp_path / "alias.py"
    alias.symlink_to(code)

    assert _run("add", str(alias), "--lines", "4", "--as", "a", "hi") == 0

    assert alias.is_symlink()
    assert "# [lma:" in code.read_text()


def test_a_save_made_while_we_compute_is_kept(code) -> None:
    saved = "import os\r\nimport sys\r\n"

    def change(text: str) -> tuple[str, int]:
        if "sys" not in text:
            code.write_bytes(saved.encode())  # an editor saves while we compute
        return text + "# end\r\n", len(text)

    result = cli._rewrite(code, change)

    assert code.read_bytes().decode() == saved + "# end\r\n"
    assert result == len(saved)


def test_a_file_that_never_settles_is_refused_and_left_alone(code) -> None:
    def change(text: str) -> tuple[str, None]:
        code.write_bytes(text.encode() + b"#\r\n")
        return "replaced", None

    with pytest.raises(cli._Refused, match="kept changing"):
        cli._rewrite(code, change)

    assert code.read_bytes().endswith(b"#\r\n#\r\n#\r\n")


def test_a_link_with_another_extension_is_read_as_the_file_it_names(code, tmp_path, capsys) -> None:
    alias = tmp_path / "alias.md"
    alias.symlink_to(code)

    assert _run("add", str(alias), "--lines", "4", "--as", "a", "hi") == 0

    assert "# [lma:" in code.read_text() and "<!--" not in code.read_text()


def test_an_add_whose_file_changes_meanwhile_is_refused_not_moved(code) -> None:
    saved = "z = 0\r\n" + code.read_bytes().decode()

    def change(text: str) -> tuple[str, None]:
        code.write_bytes(saved.encode())  # an editor saves a line above the selection
        return "anchored on the old line 1", None

    with pytest.raises(cli._Refused, match="line numbers may name other code"):
        cli._rewrite(code, change, retry=False)

    assert code.read_bytes().decode() == saved


def test_writes_are_utf_8_whatever_the_locale(code) -> None:
    code.write_bytes("# café\r\n".encode())
    script = (
        "import pathlib, sys; from lemonaid.comments import cli;"
        " cli._rewrite(pathlib.Path(sys.argv[1]), lambda t: (t + '# th\\u00e9\\r\\n', None))"
    )  # ASCII only: under the C locale, a non-ASCII command line arrives as surrogates
    env = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}

    subprocess.run([sys.executable, "-c", script, str(code)], env=env, check=True)

    assert code.read_bytes().decode() == "# café\r\n# thé\r\n"


def test_two_replies_written_at_once_both_survive(code, capsys, monkeypatch) -> None:
    """Without the lock, both writers pass their check before either renames, and the
    second rename drops the first reply."""
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    real_replace = os.replace
    renames: list[str] = []
    second_at_rename = threading.Event()

    def rename_after_the_other_writer_checks(src: str, dst: str) -> None:
        renames.append(src)
        if len(renames) == 1:
            second_at_rename.wait(timeout=1)  # the lock keeps the second writer from coming
        else:
            second_at_rename.set()
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", rename_after_the_other_writer_checks)

    def reply(body: str) -> None:
        def change(text: str) -> tuple[str, None]:
            added = edits.reply(text, "python", root, author="A (Author)", body=body)
            return edits.apply(text, added.edits), None

        cli._rewrite(code, change)

    writers = [threading.Thread(target=reply, args=(body,)) for body in ("first", "second")]
    for writer in writers:
        writer.start()
        time.sleep(0.1)
    for writer in writers:
        writer.join(timeout=10)

    bodies = {c.body for c in parse.parse(code.read_bytes().decode(), "python").comments}
    assert {"first", "second"} <= bodies


def test_a_link_retargeted_during_add_changes_only_the_file_it_first_named(
    tmp_path, monkeypatch
) -> None:
    first, second = tmp_path / "first.md", tmp_path / "second.py"
    first.write_text("hello\n")
    second.write_text("x = 1\n")
    alias = tmp_path / "alias.md"
    alias.symlink_to(first)
    real_body = cli._body

    def body_then_retarget(given: str) -> str:
        alias.unlink()
        alias.symlink_to(second)
        return real_body(given)

    monkeypatch.setattr(cli, "_body", body_then_retarget)

    assert _run("add", str(alias), "--lines", "1", "--as", "a", "hi") == 0

    assert "<!-- [lma:" in first.read_text()
    assert second.read_text() == "x = 1\n"


def _brief(tmp_path, *, watching: str = "") -> object:
    brief = tmp_path / "brief.md"
    brief.write_text(
        "# Work\nBrief-ID: HillyHad.work\n\n## Goal\n\nx\n"
        + (f"\n## Watching\n\n- `{watching}`\n" if watching else "")
    )
    return brief


def test_self_signs_as_the_author_for_a_file_the_brief_does_not_name(
    code, tmp_path, monkeypatch, capsys
) -> None:
    brief = _brief(tmp_path)
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()

    assert _run("reply", str(code), "--re", root, "--self", "because") == 0

    reply = parse.parse(code.read_text(), "python").comment(capsys.readouterr().out.strip())
    assert (reply.author, reply.by_lemon) == ("HillyHad (Author)", True)


def test_self_signs_with_the_brief_s_watch_doc_signature_for_that_file(
    tmp_path, monkeypatch, capsys
) -> None:
    doc = tmp_path / "review.md"
    doc.write_text("# Review\n\nA claim.\n")
    brief = _brief(tmp_path, watching=f"lemonaid watch doc --wait {doc} --me 'HillyHad (Reviewer)'")
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))

    assert _run("add", str(doc), "--lines", "3", "--self", "true?") == 0

    added = parse.parse(doc.read_text(), "markdown").comments[0]
    assert added.author == "HillyHad (Reviewer)"


def test_a_second_reply_must_name_the_newest_reply_it_read(code, capsys) -> None:
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    _run("reply", str(code), "--re", root, "--as", "RoastJet (Reviewer)", "because")
    theirs = capsys.readouterr().out.strip()

    refused = _run("reply", str(code), "--re", root, "--as", "HillyHad (Author)", "also because")
    said = capsys.readouterr().err
    written = _run(
        "reply", str(code), "--re", root, "--after", theirs, "--as", "HillyHad (Author)", "and"
    )

    assert refused == 2
    assert f"--after {theirs}" in said and "RoastJet (Reviewer)" in said and "because" in said
    assert written == 0
    assert len(parse.parse(code.read_text(), "python").comments) == 3


def test_a_reply_after_an_older_reply_is_refused_and_shows_the_newer_one(code, capsys) -> None:
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    _run("reply", str(code), "--re", root, "--as", "RoastJet (Reviewer)", "first")
    first = capsys.readouterr().out.strip()
    _run("reply", str(code), "--re", root, "--after", first, "--as", "Sam", "second")
    capsys.readouterr()

    refused = _run(
        "reply", str(code), "--re", root, "--after", first, "--as", "HillyHad (Author)", "x"
    )

    said = capsys.readouterr().err
    assert refused == 2 and "second" in said and "first" not in said.split("\n", 2)[-1]


def test_quote_anchors_a_phrase_in_markdown(tmp_path, capsys) -> None:
    doc = tmp_path / "review.md"
    doc.write_text("# Review\n\nThe pre-commit hook is missing.\n")

    assert (
        _run("add", str(doc), "--lines", "3", "--quote", "pre-commit hook", "--as", "Sam", "v3")
        == 0
    )

    text = doc.read_text()
    anchor = parse.parse(text, "markdown").anchors[0]
    assert text[anchor.start : anchor.end] == "pre-commit hook"


def test_quote_is_refused_in_python(code, capsys) -> None:
    refused = _run("add", str(code), "--lines", "4", "--quote", "def", "--as", "Sam", "x")

    assert refused == 2 and "only Markdown" in capsys.readouterr().err


def test_a_lemon_s_reply_shows_in_the_inbox_until_it_is_seen(
    code, tmp_path, monkeypatch, capsys
) -> None:
    from lemonaid.comments import notice
    from lemonaid.inbox import db

    brief = _brief(tmp_path)
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:hilly")
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    with db.connect() as conn:
        after_a_person_s_comment = db.get_by_channel(conn, notice.channel(code, "claude:hilly"))

    _run("reply", str(code), "--re", root, "--self", "because\nmore")
    first = capsys.readouterr().out.strip()
    with db.connect() as conn:
        shown = db.get_by_channel(conn, notice.channel(code, "claude:hilly"))
    second_status = _run("reply", str(code), "--re", first, "--self", "and another thing")
    said = capsys.readouterr()
    second = said.out.strip()
    assert second_status == 0, said.err
    notice.seen(code, [first])
    with db.connect() as conn:
        after_seeing_one = db.get_by_channel(conn, notice.channel(code, "claude:hilly"))
    unseen_after_one = notice.unread_ids(code)
    notice.seen(code, [second])
    with db.connect() as conn:
        after_seeing_both = db.get_by_channel(conn, notice.channel(code, "claude:hilly"))

    assert after_a_person_s_comment is None
    assert shown is not None and shown.message == "HillyHad (Author): because"
    assert notice.lemon_of(shown) == "claude:hilly"
    assert after_seeing_one is not None and unseen_after_one == [second]
    assert after_seeing_both is None


def test_after_compares_replies_in_file_order_not_by_their_times(code, capsys) -> None:
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    text = code.read_text()
    known = f'# {{"id": "Known", "re": "{root}", "author": "A", "at": "2026-11-20T15:02:00Z", "body": "k"}}\n'
    unread = f'# {{"id": "Unread", "re": "{root}", "author": "B", "at": "2026-11-20T15:01:00Z", "body": "u"}}\n'
    code.write_text(text + known + unread)

    refused = _run("reply", str(code), "--re", root, "--after", "Known", "--as", "C", "me too")

    assert refused == 2 and "Unread" in capsys.readouterr().err


def test_strip_marks_the_file_s_replies_read_since_they_can_no_longer_be(
    code, tmp_path, monkeypatch, capsys
) -> None:
    from lemonaid.comments import notice

    brief = _brief(tmp_path)
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:hilly")
    _run("add", str(code), "--lines", "4", "--as", "caleb.gregory", "why?")
    root = capsys.readouterr().out.strip()
    _run("reply", str(code), "--re", root, "--self", "because")
    unread_before = notice.unread_ids(code)

    _run("strip", str(code))

    assert unread_before != [] and notice.unread_ids(code) == []


def test_strip_says_so_when_the_inbox_can_t_be_updated(code, monkeypatch, capsys) -> None:
    import sqlite3

    from lemonaid.comments import notice

    def unreachable(*args):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(notice, "removed", unreachable)
    _run("add", str(code), "--lines", "4", "--as", "Sam", "why?")
    capsys.readouterr()

    status = _run("strip", str(code))

    assert status == 0 and "lma:" not in code.read_text()
    assert "inbox rows for it weren't updated" in capsys.readouterr().err


def _locked_with_events(events: list[str]):
    import contextlib

    from lemonaid import file

    real_locked = file.locked

    @contextlib.contextmanager
    def locked(path, **kwargs):
        with real_locked(path, **kwargs):
            events.append("locked")
            yield
            events.append("released")

    return locked


def test_a_lemon_s_comment_reaches_the_inbox_while_the_file_is_still_locked(
    code, tmp_path, monkeypatch, capsys
) -> None:
    """Posted after the lock, a strip could take the comment out first, and the late row
    would stay unread with nothing left to read."""
    from lemonaid import file
    from lemonaid.comments import notice

    events: list[str] = []
    monkeypatch.setattr(file, "locked", _locked_with_events(events))
    real_replied = notice.replied
    monkeypatch.setattr(
        notice, "replied", lambda *args, **kw: (events.append("posted"), real_replied(*args, **kw))
    )
    brief = _brief(tmp_path)
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:hilly")

    _run("add", str(code), "--lines", "4", "--self", "why?")

    assert events == ["locked", "posted", "released"]


def test_strip_drops_the_comments_it_removed_including_one_written_just_before(
    code, tmp_path, monkeypatch, capsys
) -> None:
    """The comments to drop come from the text the strip changed, under the lock, not from
    a read before it."""
    import contextlib

    from lemonaid import file
    from lemonaid.comments import notice

    brief = _brief(tmp_path)
    monkeypatch.setattr("lemonaid.brief.command.own_brief", lambda args: (brief, ""))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:hilly")
    _run("add", str(code), "--lines", "4", "--self", "first")
    real_locked = file.locked
    written_late = []

    @contextlib.contextmanager
    def another_lemon_writes_first(path, **kwargs):
        if not written_late:  # the other lemon's add, which takes the lock before the strip
            written_late.append(True)
            _run("add", str(code), "--lines", "1", "--self", "second")
        with real_locked(path, **kwargs):
            yield

    monkeypatch.setattr(file, "locked", another_lemon_writes_first)
    capsys.readouterr()

    _run("strip", str(code))

    assert "lma:" not in code.read_text() and notice.unread_ids(code) == []
