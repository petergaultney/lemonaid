import argparse
import json

from lemonaid.inbox import cli, db


def _lemonaid_inbox(*args: str) -> None:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    parsed = parser.parse_args(["inbox", *args])
    parsed.func(parsed)


def test_a_tool_keeps_a_row_under_a_lemon_and_marks_it_read_by_channel():
    _lemonaid_inbox(
        "add", "item:x|/g.md", "2 replies", "-n", "g.md",
        "--under", "claude:x", "--hide-when-read", "--metadata", json.dumps({"path": "/g.md"}),
    )  # fmt: skip
    with db.connect() as conn:
        row = db.get_by_channel(conn, "item:x|/g.md", unread_only=False)
    assert row is not None and row.is_unread
    assert row.metadata == {"path": "/g.md", "under": "claude:x", "hide_when_read": True}

    _lemonaid_inbox("read", "--channel", "item:x|/g.md")

    with db.connect() as conn:
        row = db.get_by_channel(conn, "item:x|/g.md", unread_only=False)
    assert row is not None and not row.is_unread
