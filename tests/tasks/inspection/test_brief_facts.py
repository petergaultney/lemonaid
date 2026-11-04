import os
from pathlib import Path

from lemonaid.inbox import db
from lemonaid.tasks.inspection import brief_facts

_NOW = 1_800_000_000.0


def _values(found) -> dict[tuple[str, str, str], tuple[str, str]]:
    return {(f["kind"], f["key"], f["field"]): (f["value"], f["availability"]) for f in found}


def _register(conn, text: str) -> Path:
    path = Path(os.environ["LEMONAID_BRIEFS_DIR"]) / "Work.alpha.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    conn.execute(
        "INSERT INTO lemon_identities (lemon_id, path) VALUES (?, ?)", ("Work.alpha", str(path))
    )
    conn.commit()
    return path


def test_a_briefs_needs_links_bring_their_files_facts(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "d").mkdir(parents=True)
    doc = vault / "d" / "decisions.md"
    comment = '{{authorId="1" author="Sam">>which?<<}}'
    doc.write_text(f"# Decisions\n\n## Pick a {{==name==}}{comment}\n\n```\n# not a heading\n```\n")
    missing = tmp_path / "gone.md"
    brief = (
        "# Work\n\nStatus: blocked\n\n## Now\n\n"
        "- Needs you: [name](obsidian://open?vault=vault&file=d%2Fdecisions%23Pick%20a%20name)"
        f" and [old]({missing}) and [web](https://example.com)\n"
    )
    with db.connect(tmp_path / "test.db") as conn:
        _register(conn, brief)
        conn.execute(
            "INSERT INTO lemon_aliases (old_id, lemon_id) VALUES ('Old.alpha', 'Work.alpha')"
        )
        found = _values(brief_facts.facts(conn, "Work.alpha", _NOW, [vault]))

    links = found[("brief", "Work.alpha", "needs_links")][0].splitlines()
    assert links == [f"{doc.resolve()}#Pick a name", str(missing.resolve())]
    assert found[("brief", "Work.alpha", "signing_names")] == ("Work Old", "known")
    assert found[("brief", "Work.alpha", "status_since")][1] == "known"
    assert found[("brief", "Work.alpha", "needs_since")][1] == "known"
    assert found[("file", str(doc.resolve()), "exists")] == ("true", "known")
    assert found[("file", str(doc.resolve()), "headings")] == ("Decisions\nPick a name", "known")
    assert found[("file", str(missing.resolve()), "exists")] == ("false", "known")
    assert found[("file", str(missing.resolve()), "headings")][1] == "unavailable"


def test_an_unregistered_brief_is_unavailable(tmp_path: Path) -> None:
    with db.connect(tmp_path / "test.db") as conn:
        found = _values(brief_facts.facts(conn, "Nobody.here", _NOW, []))

    assert {availability for _, availability in found.values()} == {"unavailable"}


def test_a_relative_needs_link_is_taken_from_the_briefs_folder(tmp_path: Path) -> None:
    with db.connect(tmp_path / "test.db") as conn:
        brief = _register(
            conn, "# Work\n\nStatus: blocked\n\n## Now\n\n- Needs: [ask](decisions.md#Pick)\n"
        )
        (brief.parent / "decisions.md").write_text("# Pick\n")
        found = _values(brief_facts.facts(conn, "Work.alpha", _NOW, []))

    doc = str((brief.parent / "decisions.md").resolve())
    assert found[("brief", "Work.alpha", "needs_links")] == (f"{doc}#Pick", "known")
    assert found[("file", doc, "exists")] == ("true", "known")
