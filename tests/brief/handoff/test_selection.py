"""Public source selectors share stable identity and reject ambiguous names."""

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief.handoff import selection
from lemonaid.inbox import db


def test_full_short_channel_and_path_select_same_source(setup, monkeypatch):
    conn, path = setup
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    full = identity.from_path(path)
    for target in (full, identity.brief_name(full), "claude:old"):
        assert selection.channel(conn, source=target) == "claude:old"
        assert selection.channel(conn, brief=target) == "claude:old"
    assert selection.channel(conn, brief=str(path)) == "claude:old"
    with pytest.raises(LookupError, match="found 0"):
        selection.channel(conn, source="MissingName")


def test_short_name_ambiguity_requires_full_id(setup, monkeypatch):
    conn, path = setup
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    full = identity.from_path(path)
    name = identity.brief_name(full)
    other = path.with_name("other.md")
    other.write_text(f"# Other\n\nBrief-ID: {name}.different\n\n## Now\n\nOther work.\n")
    db.add(conn, "claude:other", "Other", status="read")
    attached.attach(conn, "claude:other", other)
    with pytest.raises(LookupError, match=r"ambiguous.*full Lemon-ID"):
        selection.channel(conn, source=name)
    assert selection.channel(conn, source=full) == "claude:old"
