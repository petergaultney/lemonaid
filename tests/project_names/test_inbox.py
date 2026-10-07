import asyncio

from textual.widgets import DataTable

from lemonaid.brief import attached
from lemonaid.config import Config, PlaceRoot, PlacesConfig, _parse_config
from lemonaid.inbox import db
from lemonaid.inbox.tui import app, card_context, utils


def test_config_and_hook_label_area_color(tmp_path):
    config = _parse_config(
        {"places": {"roots": [{"path": str(tmp_path), "project_name": "echo project"}]}}
    )
    root = config.places.roots[0]
    assert root.project_name == "echo project"
    assert not root.has_namespace()
    part = card_context.project_part(config.places, str(tmp_path), "", "inbox", "tools/relay")
    assert part.text.plain == "tools/relay: inbox"
    assert part.keep == len("tools/relay")
    (colored,) = card_context.parts(
        ("project",), part.text, part, "", str(tmp_path), False, project_name_colors=True
    )
    assert colored.text.spans[0].style == utils.project_color("tools/relay")


def test_app_invalidates_cached_labels_after_background_lookup(tmp_path, monkeypatch):
    root = PlaceRoot(tmp_path, name="repo", project_name="printf 'tools/relay\\n'")
    monkeypatch.setattr(app, "load_config", lambda: Config(places=PlacesConfig(roots=[root])))
    inbox = app.LemonaidApp()
    with db.connect() as conn:
        n = db.add(conn, "test", "hello", metadata={"cwd": str(tmp_path), "git_branch": "main"})
    workers = []
    monkeypatch.setattr(inbox, "run_worker", lambda worker, **kwargs: workers.append(worker))
    monkeypatch.setattr(inbox, "_refresh_notifications", lambda: None)
    monkeypatch.setattr(inbox, "_refresh_history", lambda: None)
    monkeypatch.setattr(inbox, "_refresh_snoozed", lambda: None)
    assert inbox._project(n, "inbox").text.plain == "repo: inbox"
    assert inbox._project(n, "other").text.plain == "repo: other"
    assert len(workers) == 1
    asyncio.run(workers.pop())
    assert inbox._project(n, "inbox").text.plain == "tools/relay: inbox"
    assert inbox._project(n, "other").text.plain == "tools/relay: other"
    assert workers == []


def test_innermost_root_selects_its_own_hook(tmp_path, monkeypatch):
    outer = PlaceRoot(tmp_path, name="outer", project_name="echo outer-project")
    inner = PlaceRoot(tmp_path / "inner", name="inner")
    inner.path.mkdir()
    monkeypatch.setattr(
        app, "load_config", lambda: Config(places=PlacesConfig(roots=[outer, inner]))
    )
    inbox = app.LemonaidApp()
    with db.connect() as conn:
        n = db.add(conn, "test", "hello", metadata={"cwd": str(inner.path)})
    assert inbox._project(n, "").text.plain == "inner"
    assert inbox._project_names.names == {}


def test_hook_names_render_in_both_layouts_and_alternate_views(tmp_path, monkeypatch):
    root = PlaceRoot(tmp_path, name="repo", project_name="printf 'tools/relay\\n'")
    monkeypatch.setattr(app, "load_config", lambda: Config(places=PlacesConfig(roots=[root])))
    monkeypatch.setattr(app, "start_unified_watcher", lambda **kwargs: None)
    monkeypatch.setattr(app.LemonaidApp, "_archive_channel", lambda *args: None)
    monkeypatch.setattr(app.resume_mod, "has_resume_command", lambda *args: True)
    with db.connect() as conn:
        active = db.add(conn, "claude:active", "hello", "active", {"cwd": str(tmp_path)})
        archived = db.add(conn, "claude:old", "hello", "old", {"cwd": str(tmp_path)})
        snoozed = db.add(conn, "claude:snoozed", "hello", "snoozed", {"cwd": str(tmp_path)})
        for row in (active, archived, snoozed):
            path = tmp_path / f"brief-{row.id}.md"
            path.write_text("# Task\n\nStatus: waiting\n\nArea: subarea\n\n## Now\n")
            attached.attach(conn, row.channel, path)
        db.archive(conn, archived.id)
        db.snooze(conn, snoozed.id, 9999999999)
        conn.execute("UPDATE notifications SET switch_source = 'tmux'")
        conn.commit()

    async def run(width):
        inbox = app.LemonaidApp()
        async with inbox.run_test(size=(width, 35)) as pilot:
            await inbox.workers.wait_for_complete()
            await pilot.pause()
            table = inbox.query_one("#main_table", DataTable)
            assert "tools/relay: subarea" in " ".join(
                str(cell) for cell in table.get_row(str(active.id))
            )
            inbox._refresh_history()
            table = inbox.query_one("#history_table", DataTable)
            assert "tools/relay: subarea" in " ".join(
                str(cell) for cell in table.get_row(str(archived.id))
            )
            inbox._refresh_snoozed()
            table = inbox.query_one("#snoozed_table", DataTable)
            assert "tools/relay: subarea" in " ".join(
                str(cell) for cell in table.get_row(str(snoozed.id))
            )

    asyncio.run(run(160))
    asyncio.run(run(44))
