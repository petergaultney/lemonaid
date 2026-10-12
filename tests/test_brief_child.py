"""`brief new --child`: an unattached brief from a template, its parent filled in."""

import argparse
import contextlib
import datetime
import json
import shlex
from pathlib import Path

import pytest

from lemonaid import groups, obsidian
from lemonaid.brief import attached, child, identity, output_doc, status, write_cli
from lemonaid.inbox import db

_PARENT = "hq.BlessBar"
_PR = "https://github.com/acme/widgets/pull/12"


def _run(capsys, *argv: str, err: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["new", *argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    out, stderr = capsys.readouterr()
    if err is not None:
        err.append(stderr)

    return json.loads(out)


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
        f"# Fix the widget\n\nBrief-ID: {result['lemon_id']}\n\n"
        f"Parent: {_PARENT}, {datetime.date.today().isoformat()}\n\n## Goal\n"
    )
    assert "## Now" not in text
    assert text.rstrip().endswith("## Waiters")
    assert result["parent"] == _PARENT


def test_area_goes_in_the_header_where_the_card_reads_it(capsys, parent):
    result = _run(capsys, "--child", "--parent", _PARENT, "--area", "apps/web", "Fix the widget")

    text = Path(result["path"]).read_text()
    assert f"{datetime.date.today().isoformat()}\n\nArea: apps/web\n\n## Goal\n" in text
    assert status.split(text).area == "apps/web"


def test_a_child_brief_is_attached_to_no_one(capsys, parent):
    result = _run(capsys, "--child", "--parent", _PARENT, "Fix the widget")

    with db.connect() as conn:
        assert all(a.path != Path(result["path"]) for a in attached.everything(conn))
        assert identity.ensure(conn, Path(result["path"])) == result["lemon_id"]


def test_a_child_brief_joins_its_parents_groups(capsys, parent):
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "Widgets"), [_PARENT])

    result = _run(capsys, "--child", "--parent", _PARENT, "Fix the widget")

    with db.connect() as conn:
        assert groups.store.names_of(conn, result["lemon_id"]) == ("Widgets",)
    assert groups.line.read(Path(result["path"]).read_text()) == ("Widgets",)


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
        "--output-doc",
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
    assert "a bare `--codex-thread` for Codex (no `$CODEX_THREAD_ID`" in text
    assert "`git range-diff origin/<base> <reviewed sha> HEAD`" in text


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


def test_an_output_doc_outside_every_vault_is_a_code_span(tmp_path):
    doc = tmp_path / "review.md"

    assert child.output_doc_values(str(doc), [tmp_path / "vault"])["output_doc_link"] == (
        f"`{doc}`"
    )


def test_obsidian_url_names_the_vault_by_its_folder(tmp_path):
    assert obsidian.obsidian_url(tmp_path / "trove" / "a b" / "c.md", [tmp_path / "trove"]) == (
        "obsidian://open?vault=trove&file=a%20b%2Fc"
    )


def test_the_output_doc_argument_survives_an_apostrophe(tmp_path):
    doc = tmp_path / "Sam's review.md"

    assert shlex.split(child.output_doc_values(str(doc), [])["output_doc_arg"]) == [str(doc)]


def test_an_output_doc_is_recorded_beside_the_parent_line(capsys, parent):
    result = _run(capsys, "--child", "--parent", _PARENT, "--output-doc", "/tmp/doc.md", "Write it")

    text = Path(result["path"]).read_text()
    assert "\nOutput-Doc: /tmp/doc.md\n" in text
    assert output_doc.of_brief(Path(result["path"])) == Path("/tmp/doc.md")


def test_review_doc_still_works_but_warns(capsys, parent):
    err: list[str] = []
    result = _run(
        capsys, "--child", "--parent", _PARENT, "--review-doc", "/tmp/doc.md", "Write it", err=err
    )

    assert output_doc.of_brief(Path(result["path"])) == Path("/tmp/doc.md")
    assert "--review-doc is deprecated; use --output-doc" in err[0]


def test_a_brief_without_an_output_doc_reads_as_none():
    assert output_doc.read("# T\n\nParent: x\n\n## Goal\n\nOutput-Doc: /ignored\n") is None
