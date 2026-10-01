"""`brief new --child`: an unattached brief from a template, its parent filled in."""

import argparse
import contextlib
import datetime
import json
import shlex
from pathlib import Path

import pytest

from lemonaid.brief import attached, child, identity, links, write_cli
from lemonaid.inbox import db

_PARENT = "hq.BlessBar"
_PR = "https://github.com/acme/widgets/pull/12"


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["new", *argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


@pytest.fixture
def parent(monkeypatch, tmp_path):
    """A parent brief registered under `_PARENT`, the way `brief id` leaves one."""
    path = tmp_path / "briefs" / "2026-09-01-hq.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# hq\n\nLemon-ID: {_PARENT}\n\nStatus: working\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
    return path


def test_a_child_brief_has_the_header_and_no_now(capsys, parent):
    result = _run(capsys, "--child", "--parent", _PARENT, "Fix the widget")

    path = Path(result["path"])
    text = path.read_text()
    assert path.name == f"{datetime.date.today().isoformat()}-fix-the-widget.md"
    assert text.startswith(
        f"# Fix the widget\n\nLemon-ID: {result['lemon_id']}\n\nStatus: working\n\n"
        f"Parent: {_PARENT}, {datetime.date.today().isoformat()}\n\n## Goal\n"
    )
    assert "## Now" not in text
    assert text.rstrip().endswith("## Waiters")
    assert result["parent"] == _PARENT


def test_a_child_brief_is_attached_to_no_one(capsys, parent):
    result = _run(capsys, "--child", "--parent", _PARENT, "Fix the widget")

    with db.connect() as conn:
        assert all(a.path != Path(result["path"]) for a in attached.everything(conn))
        assert identity.ensure(conn, Path(result["path"])) == result["lemon_id"]


def test_the_review_template_fills_the_pr_doc_and_waiters(capsys, parent, tmp_path):
    vault = tmp_path / "notes"
    (tmp_path / "config.toml").write_text(f'[brief]\nvaults = ["{vault}"]\n')
    doc = vault / "reviews" / "widgets-12.md"

    result = _run(
        capsys,
        "--child",
        "--template",
        "review",
        "--parent",
        _PARENT,
        "--pr",
        _PR,
        "--review-doc",
        str(doc),
        "--author",
        "widget.QuickOdd",
        "--slug",
        "review-widgets-12",
        "Review widgets #12",
    )

    text = Path(result["path"]).read_text()
    wordybin = result["lemon_id"].rsplit(".", 1)[1]
    assert Path(result["path"]).name.endswith("-review-widgets-12.md")
    assert f"[widgets#12]({_PR})" in text
    assert "[widgets-12](obsidian://open?vault=notes&file=reviews%2Fwidgets-12)" in text
    assert f"`lemonaid tell {_PARENT}` and `lemonaid tell widget.QuickOdd`" in text
    assert f"--wait 12 --repo acme/widgets --head <head SHA> --me 'Reviewer ({wordybin})'" in text
    assert f"--wait {doc} --me 'Reviewer ({wordybin})'" in text
    assert '"$CODEX_THREAD_ID"' in text


def test_a_template_value_without_its_flag_is_refused_before_writing(capsys, parent):
    result = _run(capsys, "--child", "--template", "review", "--parent", _PARENT, "Review it")

    assert "pass --pr" in result["error"]
    assert not list(parent.parent.glob("*-review-it.md"))


def test_an_existing_brief_is_never_overwritten(capsys, parent):
    first = _run(capsys, "--child", "--parent", _PARENT, "Same")
    Path(first["path"]).write_text("edited\n")

    second = _run(capsys, "--child", "--parent", _PARENT, "Same")

    assert "already exists" in second["error"]
    assert Path(first["path"]).read_text() == "edited\n"


def test_a_user_template_replaces_the_packaged_one(capsys, parent, tmp_path, monkeypatch):
    users = tmp_path / "templates"
    users.mkdir()
    (users / "child.md").write_text("## Goal\n\nFor $parent_id on $date.\n")
    monkeypatch.setattr(child, "user_dir", lambda: users)

    result = _run(capsys, "--child", "--parent", _PARENT, "Mine")

    assert (
        f"For {_PARENT} on {datetime.date.today().isoformat()}." in Path(result["path"]).read_text()
    )


def test_an_unknown_template_lists_the_ones_there_are(capsys, parent):
    assert "child, review" in _run(capsys, "--child", "--template", "nope", "x")["error"]


def test_child_refuses_an_attach_target(capsys, parent):
    assert "--parent" in _run(capsys, "--child", "--self", "x")["error"]


def test_child_options_need_child(capsys, parent):
    assert _run(capsys, "--self", "--pr", "1", "x")["error"] == "--pr needs --child"


def test_a_pr_number_needs_a_repo():
    with pytest.raises(child.Problem):
        child.pr_values("12", "")

    assert child.pr_values("12", "acme/widgets")["pr_url"] == _PR


def test_a_review_doc_outside_every_vault_is_a_code_span(tmp_path):
    doc = tmp_path / "review.md"

    assert child.review_doc_values(str(doc), [tmp_path / "vault"])["review_doc_link"] == (
        f"`{doc}`"
    )


def test_obsidian_url_names_the_vault_by_its_folder(tmp_path):
    assert links.obsidian_url(tmp_path / "trove" / "a b" / "c.md", [tmp_path / "trove"]) == (
        "obsidian://open?vault=trove&file=a%20b%2Fc"
    )


def test_the_review_doc_argument_survives_an_apostrophe(tmp_path):
    doc = tmp_path / "Sam's review.md"

    assert shlex.split(child.review_doc_values(str(doc), [])["review_doc_arg"]) == [str(doc)]
