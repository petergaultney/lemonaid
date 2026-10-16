"""Saved-answer controls and help from the actual popup and inbox brief views."""

import asyncio
import datetime

from textual.containers import VerticalScroll
from textual.widgets import Static

from lemonaid import config, keys
from lemonaid.brief import answer_archive, answers, store, target
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs import brief_help, brief_popup
from lemonaid.inbox.tui.briefs.brief_view import BriefView
from lemonaid.inbox.tui.help_screen import HelpScreen

from ..shared import lemons, until


def _brief(name="task"):
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "# Task\n\n## Now\n\nKeep this.\n\n## Goal\n\nTask goal.\n"
    for index in range(2):
        text = answers.add(
            text,
            f"Question {index}?",
            f"Saved answer {index}",
            datetime.datetime(2026, 10, 15, 12, index),
        )
    path.write_text(text)
    return path


def _popup(path, cfg=None):
    return brief_popup.BriefPopup(
        target.Target([path], [], None, [], "Task"), cfg or config.Config()
    )


def _text(screen):
    return "\n".join(str(widget.render()) for widget in screen.query(Static))


def test_popup_archives_one_all_and_toggles_archives_without_restoring():
    path = _brief()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("A")
            await pilot.pause()
            assert "Saved answer 1" not in path.read_text()
            assert "Saved answer 0" in path.read_text()
            assert len(answer_archive.read(path)) == 1
            view = app.query_one(BriefView)
            assert "Saved answer 1" not in "\n".join(item.body for item in view._items)
            await pilot.press("e")
            await pilot.pause()
            assert "Saved answer 1" in "\n".join(item.body for item in view._items)
            assert sum(item.kind == "archived" for item in view._items) == 1
            assert "Saved answer 1" not in path.read_text()
            await pilot.press("e", "ctrl+a")
            await pilot.pause()
            assert len(answer_archive.read(path)) == 2
            assert "Saved answer" not in path.read_text()
            assert "Saved answer" not in "\n".join(item.body for item in view._items)
            assert "Keep this." in path.read_text() and "Task goal." in path.read_text()
            await pilot.press("e")
            await pilot.pause()
            assert "Saved answer 0" in "\n".join(item.body for item in view._items)
            assert "Saved answer 1" in "\n".join(item.body for item in view._items)

    asyncio.run(run())


def test_popup_help_shows_its_keys_and_returns_to_the_brief():
    path = _brief()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(80, 35)) as pilot:
            await pilot.pause()
            await pilot.press("?")
            assert isinstance(app.screen, brief_help.BriefHelpScreen)
            text = _text(app.screen)
            assert "Brief keys" in text
            assert "Archive the selected live saved answer" in text
            assert "Pinning" not in text and "Groups" not in text
            assert "Scroll the brief" in text
            for close in ("?", "q", "escape"):
                await pilot.press(close)
                assert not isinstance(app.screen, HelpScreen)
                assert app.is_running
                await pilot.press("?")
            await pilot.press("escape", "q")

    asyncio.run(run())


def test_sidebar_help_and_archive_controls_do_not_act_on_the_inbox(monkeypatch, tmp_path):
    lemons(monkeypatch, tmp_path, 1)
    path = _brief()
    found = target.Target([path], [], None, [], "Task")
    monkeypatch.setattr(target, "for_notification", lambda *args: found)

    async def run():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.press("b")
            await until(pilot, lambda: app._brief_target is not None)
            await pilot.press("?")
            assert isinstance(app.screen, brief_help.BriefHelpScreen)
            assert "Browse briefs" in _text(app.screen)
            assert "Groups" not in _text(app.screen)
            await pilot.press("escape", "A", "ctrl+a")
            await pilot.pause()
            assert len(answer_archive.read(path)) == 2
            assert app._brief_target is not None
            await pilot.press("e")
            await pilot.pause()
            assert "Saved answer 1" in "\n".join(
                item.body for item in app.query_one(BriefView)._items
            )
            await pilot.press("q", "?")
            assert isinstance(app.screen, HelpScreen)
            assert not isinstance(app.screen, brief_help.BriefHelpScreen)
            assert "Groups" in _text(app.screen)

    asyncio.run(run())


def test_archive_write_failure_preserves_live_view(monkeypatch):
    path = _brief()
    before = path.read_text()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(answer_archive, "save", fail)

    async def run():
        app = _popup(path)
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            await pilot.press("A")
            await pilot.pause()
            assert path.read_text() == before
            assert "Saved answer 1" in "\n".join(
                item.body for item in app.query_one(BriefView)._items
            )
            assert app.is_running

    asyncio.run(run())


def test_multi_brief_archiving_only_changes_first_and_expansion_resets():
    first, second = _brief("first"), _brief("second")

    async def run():
        app = brief_popup.BriefPopup(
            target.Target([first, second], [], None, [], "Both"), config.Config()
        )
        async with app.run_test(size=(80, 35)) as pilot:
            view = app.query_one(BriefView)
            await pilot.pause()
            displayed = view._sections[0].path
            other = first if displayed == second else second
            await pilot.press("A", "e")
            await pilot.pause()
            assert len(answer_archive.read(displayed)) == 1
            assert not answer_archive.path_for(other).exists()
            assert sum(item.kind == "archived" for item in view._items) == 1
            view.show(target.Target([other], [], None, [], "Other"))
            await pilot.pause()
            assert view._answers_expanded is False

    asyncio.run(run())


def test_rebound_keys_work_and_help_names_the_live_config():
    path = _brief()
    cfg = config.Config()
    cfg.tui.keybindings.answer_archive = "ctrl+k"
    cfg.tui.keybindings.answer_archive_all = "ctrl+l"
    cfg.tui.keybindings.answers_expand = "ctrl+x"

    async def run():
        app = _popup(path, cfg)
        async with app.run_test(size=(80, 35)) as pilot:
            await pilot.pause()
            await pilot.press("A")
            assert not answer_archive.path_for(path).exists()
            await pilot.press("ctrl+k", "ctrl+x")
            await pilot.pause()
            assert sum(item.kind == "archived" for item in app.query_one(BriefView)._items) == 1
            await pilot.press("?")
            text = _text(app.screen)
            assert "ctrl+k" in text and "Archive the selected" in text
            assert "ctrl+x" in text and "Expand or collapse" in text
            await pilot.press("escape", "ctrl+l")
            assert len(answer_archive.read(path)) == 2

    asyncio.run(run())


def test_answer_key_conflicts_are_reported_and_defaults_are_clear(tmp_path, capsys):
    assert keys.conflicts(config.KeybindingsConfig()) == []
    file = tmp_path / "config.toml"
    file.write_text('[tui.keybindings]\nanswer_archive = "a"\nanswers_expand = "d"\n')
    cfg = config.load_config(file)
    assert cfg.tui.keybindings.answer_archive == "a"
    warning = capsys.readouterr().err
    assert "answer and answer_archive" in warning
    assert "more_detail and answers_expand" in warning


def test_archive_keys_do_not_edit_answers_while_a_dialog_is_open():
    path = _brief()
    path.write_text(
        path.read_text()
        .replace("Keep this.", "### Needs you\n\n- Choice: pick one")
        .replace("## Goal", "## Questions\n\n### Choice\n\nContext.\n\n## Goal")
    )
    before = path.read_text()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(80, 35)) as pilot:
            await pilot.pause()
            await pilot.press("a", "A", "e", "ctrl+a")
            assert path.read_text() == before
            assert not answer_archive.path_for(path).exists()
            await pilot.press("escape", "?", "A", "ctrl+a", "e")
            assert path.read_text() == before
            assert not answer_archive.path_for(path).exists()

    asyncio.run(run())


def test_brief_help_scrolls_in_a_narrow_pane():
    path = _brief()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(35, 18)) as pilot:
            await pilot.pause()
            await pilot.press("?")
            scroll = app.screen.query_one(VerticalScroll)
            await pilot.pause()
            assert scroll.max_scroll_y > 0
            await pilot.press("end")
            await pilot.pause()
            assert scroll.scroll_y > 0
            await pilot.press("escape")
            assert app.is_running

    asyncio.run(run())
