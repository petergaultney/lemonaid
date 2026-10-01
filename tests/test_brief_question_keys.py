"""Choosing a question in a brief view and answering it, sent as `lemonaid tell` sends."""

import asyncio
from pathlib import Path

from textual.widgets import Input

from lemonaid import config as config_mod
from lemonaid import keys
from lemonaid.brief import attached, identity, target
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.inbox.tui import brief_popup
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.brief_questions import AnswerScreen
from lemonaid.inbox.tui.brief_view import BriefView
from lemonaid.messages import store

from .test_brief_navigation import _lemons, _until

_BRIEF = """\
# Ship it

Status: blocked

## Now

### Needs Peter

- retry policy: which one?
- rename the flag
- an aside

## Questions

### retry policy

- **Context:** retries pile up.

### rename the flag

- **Context:** two names for one thing.
"""


def _attached_brief(text: str = _BRIEF) -> tuple[Path, Path]:
    """A brief attached to a lemon, and the inbox its messages land in."""
    path = brief_store.briefs_dir() / "ship-it.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    with db.connect() as conn:
        db.add(conn, "claude:ship", "", metadata={})
        attached.attach(conn, "claude:ship", path)
        inbox = store.inbox_for_id(identity.ensure(conn, path))
    return path, inbox


def _messages(inbox: Path) -> list[str]:
    return [p.read_text().split("\n\n", 1)[1].strip() for p in sorted(inbox.glob("*.md"))]


def _popup(path: Path, cfg: config_mod.Config | None = None) -> brief_popup.BriefPopup:
    found = target.Target([path], [path.parent], None, [], "Ship it")
    return brief_popup.BriefPopup(found, cfg or config_mod.Config(), [("ctrl+b", "b")])


def _needs(app: brief_popup.BriefPopup) -> str:
    view = app.query_one(BriefView)
    return view._needs_markdown(view._sections[0])


def test_the_first_question_starts_selected_and_the_keys_move_and_ask():
    path, inbox = _attached_brief()

    async def run() -> None:
        app = _popup(path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert "- ▶ retry policy: which one?" in _needs(app)
            assert "**Context:** retries pile up." in _needs(app)

            await pilot.press("]", "]")
            assert "- ▶ rename the flag" in _needs(app)  # an aside has no entry to land on

            await pilot.press("d")
            await pilot.press("[", "a")
            assert isinstance(app.screen, AnswerScreen)
            app.screen.query_one(Input).value = "exponential, capped at 5"
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(run())

    assert _messages(inbox) == [
        "More detail needed on rename the flag: rewrite that entry in ## Questions",
        "Answer to retry policy: exponential, capped at 5\n\n"
        'This answers "retry policy". Your brief says `blocked` on: "rename the flag", '
        '"an aside". Update Status if that changes.',
    ]


def test_escape_in_the_answer_box_sends_nothing_and_keeps_the_popup():
    path, inbox = _attached_brief()

    async def run() -> None:
        app = _popup(path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("a", "x", "escape")
            await pilot.pause()
            assert not isinstance(app.screen, AnswerScreen)
            assert app.is_running

    asyncio.run(run())

    assert _messages(inbox) == []


def test_without_questions_the_keys_do_nothing_and_no_hint_shows():
    path, inbox = _attached_brief("# Old\n\nStatus: blocked\n\n## Now\n\n- Needs Peter: pick one\n")

    async def run() -> None:
        app = _popup(path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("]", "d", "a")
            await pilot.pause()
            assert not isinstance(app.screen, AnswerScreen)
            assert not app.query(".brief-question-keys")

    asyncio.run(run())

    assert _messages(inbox) == []


def test_the_keys_come_from_config_and_the_hint_names_them():
    path, _ = _attached_brief()
    cfg = config_mod.Config()
    cfg.tui.keybindings.question_previous = "("
    cfg.tui.keybindings.question_next = ")"

    async def run() -> None:
        app = _popup(path, cfg)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press(")")
            assert "- ▶ rename the flag" in _needs(app)
            hint = app.query_one(".brief-question-keys")
            assert "( ) question · a answer · d more detail" in str(hint.render())

    asyncio.run(run())


def test_the_key_that_opened_the_popup_closes_it():
    path, _ = _attached_brief()

    async def run() -> bool:
        app = _popup(path)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+b", "b")
            await pilot.pause()
            return app.is_running

    assert asyncio.run(run()) is False


def test_a_key_bound_twice_in_one_view_is_reported(tmp_path, capsys):
    (tmp_path / "c.toml").write_text('[tui.keybindings]\nup_down = "ad"\nquestion_next = ")"\n')

    cfg = config_mod.load_config(tmp_path / "c.toml")

    assert cfg.tui.keybindings.question_next == ")"
    err = capsys.readouterr().err
    assert "in the brief view, 'a' is bound to up and answer" in err
    assert "in the brief view, 'd' is bound to down and more_detail" in err
    assert "in the inbox view, 'a' is bound to up and archive" in err


def test_the_defaults_collide_with_no_common_up_down_choice():
    for up_down in ("", "kj"):
        assert keys.conflicts(config_mod.KeybindingsConfig(up_down=up_down)) == []
    assert keys.conflicts(config_mod.KeybindingsConfig(up_down="ri", rename="n")) == []


def test_a_named_key_and_its_character_are_one_key():
    kb = config_mod.KeybindingsConfig(question_previous="left_parenthesis", question_next="(")

    assert keys.conflicts(kb) == [
        "in the brief view, '(' is bound to question_previous and question_next"
    ]


def test_the_scratch_pane_brief_takes_the_same_keys(monkeypatch, tmp_path):
    _lemons(monkeypatch, tmp_path, 1)
    path, inbox = _attached_brief()
    monkeypatch.setattr(
        target, "for_notification", lambda *args: target.Target([path], [], None, [], "Ship it")
    )

    async def run() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.press("tab")
            await _until(pilot, lambda: app._brief_target is not None)
            await pilot.pause()
            await pilot.press("]", "a")
            assert isinstance(app.screen, AnswerScreen)
            app.screen.query_one(Input).value = "yes"
            await pilot.press("enter")
            await pilot.pause()
            assert app._brief_target is not None  # `a` answered rather than archiving

    asyncio.run(run())

    assert _messages(inbox) == [
        "Answer to rename the flag: yes\n\n"
        'This answers "rename the flag". Your brief says `blocked` on: "retry policy", '
        '"an aside". Update Status if that changes.'
    ]


def test_the_popup_shows_a_pr_state_that_arrives_after_it_opens():
    path, _ = _attached_brief(_BRIEF.replace("- an aside", "- an aside on PR #124"))
    cfg = config_mod.Config()
    cfg.brief.pr_state = "printf merged"

    async def run() -> tuple[tuple[str, str], ...]:
        app = _popup(path, cfg)
        async with app.run_test(size=(100, 40)) as pilot:
            view = app.query_one(BriefView)
            for _ in range(200):
                if view._sections and view._sections[0].prs == (("#124", "merged"),):
                    break
                await pilot.pause(0.02)
            return view._sections[0].prs

    assert asyncio.run(run()) == (("#124", "merged"),)
