"""`lemonaid docs`: a session's deliveries, who holds a doc, and the table."""

import argparse

import pytest

from lemonaid.docs import cli, deliveries, paths

from ..shared import configure, doc

_SESSION = "0f0e0d0c-1111-2222-3333-444455556666"


def _docs(*argv: str) -> None:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["docs", *argv])
    args.func(args)


def _line(window: int, **fields) -> dict:
    base = {"at": "2026-01-05T09:30:00-05:00", "harness": "claude", "session": _SESSION}
    return {**base, "window": window, "mode": "classic", "shadow": False, **fields}


@pytest.fixture
def log(tmp_path):
    deliveries.append(
        [
            _line(1, kind="window", source="startup", cwd=str(tmp_path), packages=["core"]),
            _line(
                1,
                kind="doc",
                doc="/docs/voice.md",
                section="",
                package="core",
                delivery="full",
                chars=14,
                shadow=True,
            ),
            _line(2, kind="window", source="compact", cwd=str(tmp_path), packages=["core"]),
            _line(
                2,
                kind="doc",
                doc="/docs/prs.md",
                section="Drafts",
                trigger="command ^gh pr create",
                delivery="refuse",
                chars=27,
            ),
        ]
    )


@pytest.mark.usefixtures("log")
def test_a_session_by_prefix_or_channel(capsys):
    _docs(_SESSION[:8])
    by_prefix = capsys.readouterr().out
    _docs(f"claude:{_SESSION[:8]}")

    assert capsys.readouterr().out == by_prefix
    assert "voice.md  (package core, 14 chars, shadow: not delivered)" in by_prefix
    assert "window 2: compact" in by_prefix
    assert "refuse    /docs/prs.md#Drafts  (command ^gh pr create, 27 chars)" in by_prefix


@pytest.mark.usefixtures("log")
def test_an_unknown_session_exits_with_how_many_matched():
    with pytest.raises(SystemExit, match="0 sessions"):
        _docs("ffff")


@pytest.mark.usefixtures("log")
def test_who_holds_a_doc_in_its_current_window(capsys):
    _docs("who", "prs", "--all")
    assert _SESSION in capsys.readouterr().out

    _docs("who", "voice.md", "--all")
    assert capsys.readouterr().out.startswith("No lemon holds voice.md")

    _docs("who", "prs")
    assert capsys.readouterr().out.startswith("No live lemon holds prs")


def test_the_table(tmp_path, capsys):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "prs.md", {"package": "author", "load-when": [{"command": "^gh pr (create|ready)"}]})
    configure([root])

    _docs("table")

    out = capsys.readouterr().out
    assert "| core | every lemon |" in out
    assert "| author | command `^gh pr (create\\|ready)` |" in out
    assert paths.index().exists()
