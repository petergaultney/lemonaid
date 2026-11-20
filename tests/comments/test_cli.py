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


@pytest.mark.parametrize(
    ("text", "lines", "selected"),
    [
        ("a\n\nb\n", "2", ""),
        ("a\nbc\n", "2", "bc"),
        ("a\r\nbc\r\n", "1-2", "a\r\nbc"),
        ("a\nbc", "2", "bc"),
        ("a\r\n", "1", "a"),
    ],
)
def test_lines_select_whole_lines_without_their_last_line_ending(text, lines, selected) -> None:
    start, end = cli._line_range(text, lines)

    assert text[start:end] == selected


@pytest.mark.parametrize(
    ("text", "lines"), [("a\n", "2"), ("a\r\n", "2"), ("", "1"), ("a\nb", "2-1")]
)
def test_lines_past_the_last_line_are_refused(text, lines) -> None:
    with pytest.raises(cli._Refused):
        cli._line_range(text, lines)


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
        " cli._rewrite(pathlib.Path(sys.argv[1]), lambda t: (t + '# thé\\r\\n', None))"
    )
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
