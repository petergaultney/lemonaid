from lemonaid.brief import attached
from lemonaid.inbox import db, parent_order
from lemonaid.lineage import links


def test_parent_ids_resolve_through_current_brief_attachments(tmp_path):
    with db.connect() as conn:
        for name in ("parent", "child", "unrelated"):
            path = tmp_path / f"{name}.md"
            conn.execute(
                "INSERT INTO lemon_identities (path, lemon_id) VALUES (?, ?)",
                (str(path), f"{name}.Id"),
            )
            attached.attach(conn, f"claude:{name}", path)
        links.set_parent(conn, "child.Id", "parent.Id")
        links.set_parent(conn, "unrelated.Id", "missing.Id")

        assert parent_order.channels(conn) == {"claude:child": "claude:parent"}
        attached.attach(conn, "codex:resumed", tmp_path / "parent.md")
        assert parent_order.channels(conn) == {"claude:child": "codex:resumed"}
