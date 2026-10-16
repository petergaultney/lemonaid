"""Mouse selection and main actions share the keyboard's selected entry."""

import asyncio

from textual.widgets import Static
from textual.widgets._markdown import MarkdownParagraph

from lemonaid.brief import answer_archive
from lemonaid.inbox.tui.briefs import brief_view
from lemonaid.inbox.tui.briefs.brief_item_widget import ItemView
from lemonaid.inbox.tui.briefs.brief_questions import AnswerScreen
from lemonaid.inbox.tui.briefs.brief_view import BriefView

from .test_brief_answer_keys import _brief, _popup


def _with_needs():
    path = _brief()
    path.write_text(
        path.read_text().replace(
            "Keep this.", "### Needs you\n\n- First: choose one\n- Second: another choice"
        )
    )
    return path


def test_keyboard_selects_all_needs_and_saved_answers_with_obvious_action_target():
    path = _with_needs()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            assert view._selected_item().label == "First"
            assert len(view.query("ItemView.-selected")) == 1
            assert "Selected Needs: First" in view._selection_hint()
            await pilot.press("A")
            assert not answer_archive.path_for(path).exists()
            await pilot.press("]", "a")
            assert isinstance(app.screen, AnswerScreen)
            assert app.screen._label == "Second"
            await pilot.press("escape", "]")
            assert view._selected_item().kind == "answer"
            assert "archive this answer" in view._selection_hint()
            await pilot.press("]", "A")
            await pilot.pause()
            assert "Saved answer 0" not in path.read_text()
            assert "Saved answer 1" in path.read_text()
            assert "Saved answer 0" in answer_archive.read(path)[0]

    asyncio.run(run())


def test_mouse_selects_a_need_then_clicking_selected_need_opens_its_answer_box():
    path = _with_needs()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 50)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            widget = next(
                w
                for w in view.query(ItemView)
                if w.item.kind == "need" and w.item.label == "Second"
            )
            title = widget.query_one(".item-title", Static)
            await pilot.click(title, offset=(2, 0))
            assert view._selected_item().label == "Second"
            assert widget.has_class("-selected")
            assert not isinstance(app.screen, AnswerScreen)
            await pilot.pause(0.6)
            await pilot.click(title, offset=(2, 0))
            await pilot.pause(0.7)
            assert isinstance(app.screen, AnswerScreen)
            assert app.screen._label == "Second"

    asyncio.run(run())


def test_clicking_selected_saved_answer_archives_that_answer_only():
    path = _brief()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 55)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            widget = next(w for w in view.query(ItemView) if w.item.label == "Question 0?")
            title = widget.query_one(".item-title", Static)
            title.scroll_visible(animate=False)
            await pilot.pause()
            await pilot.click(title, offset=(2, 0))
            assert view._selected_item().label == "Question 0?"
            await pilot.pause(0.6)
            await pilot.click(title, offset=(2, 0))
            await pilot.pause(0.7)
            assert "Saved answer 0" not in path.read_text()
            assert "Saved answer 1" in path.read_text()

    asyncio.run(run())


def test_double_clicking_selected_text_does_not_activate_it():
    path = _brief()
    before = path.read_text()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 55)) as pilot:
            await pilot.pause()
            widget = app.query_one("ItemView.-selected", ItemView)
            title = widget.query_one(".item-title", Static)
            await pilot.click(title, offset=(2, 0), times=2)
            await pilot.pause(0.7)
            assert path.read_text() == before
            assert not answer_archive.path_for(path).exists()

    asyncio.run(run())


def test_archive_refuses_a_selected_answer_changed_since_display():
    path = _brief()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 55)) as pilot:
            await pilot.pause()
            path.write_text(path.read_text().replace("Saved answer 1", "Updated answer 1"))
            await pilot.press("A")
            assert "Updated answer 1" in path.read_text()
            assert "Saved answer 0" in path.read_text()
            assert not answer_archive.path_for(path).exists()

    asyncio.run(run())


def test_clicking_a_link_keeps_link_behavior_without_selecting_or_archiving(monkeypatch):
    path = _with_needs()
    path.write_text(
        path.read_text().replace("Saved answer 0", "See [the result](https://example.com/result).")
    )
    opened = []
    monkeypatch.setattr(brief_view, "open_link", opened.append)

    async def run():
        app = _popup(path)
        async with app.run_test(size=(110, 60)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            before = view._selected
            paragraph = next(
                p for p in view.query(MarkdownParagraph) if "the result" in p._content.plain
            )
            paragraph.scroll_visible(animate=False)
            await pilot.pause()
            await pilot.click(
                paragraph, offset=(paragraph._content.plain.index("the result") + 1, 0)
            )
            await pilot.pause(0.7)
            assert view._selected == before
            assert not answer_archive.path_for(path).exists()
            assert opened == ["https://example.com/result"]

    asyncio.run(run())


def test_dragging_text_does_not_activate_or_change_the_selected_entry():
    path = _with_needs()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 55)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            before = view._selected
            widget = next(w for w in view.query(ItemView) if w.item.label == "Second")
            title = widget.query_one(".item-title", Static)
            await pilot.mouse_down(title, offset=(2, 0))
            await pilot.hover(title, offset=(12, 0))
            await pilot.mouse_up(title, offset=(12, 0))
            await pilot.pause(0.7)
            assert view._selected == before
            assert not isinstance(app.screen, AnswerScreen)
            assert not answer_archive.path_for(path).exists()

    asyncio.run(run())


def test_clicking_need_body_selects_it_and_archived_answer_click_collapses():
    path = _with_needs()

    async def run():
        app = _popup(path)
        async with app.run_test(size=(100, 55)) as pilot:
            await pilot.pause()
            view = app.query_one(BriefView)
            paragraph = next(
                p
                for p in view.query(MarkdownParagraph)
                if "Second: another choice" in p._content.plain
            )
            await pilot.click(paragraph, offset=(3, 0))
            assert view._selected_item().label == "Second"
            await pilot.press("]", "A", "e")
            await pilot.pause()
            widget = next(w for w in view.query(ItemView) if w.item.kind == "archived")
            title = widget.query_one(".item-title", Static)
            title.scroll_visible(animate=False)
            await pilot.pause()
            await pilot.click(title, offset=(2, 0))
            assert view._selected_item().kind == "archived"
            await pilot.pause(0.6)
            await pilot.click(title, offset=(2, 0))
            await pilot.pause(0.7)
            assert view._answers_expanded is False
            assert len(answer_archive.read(path)) == 1

    asyncio.run(run())
