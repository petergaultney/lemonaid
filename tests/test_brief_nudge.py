"""The reminder of what a brief's Status waits on, and the answers that carry it."""

from lemonaid.brief import nudge, store
from lemonaid.inbox.tui import brief_questions

_BLOCKED = """\
# Ship it

Status: blocked

## Now

### Needs Peter

- **render timeouts owner:** who fixes the rebuild?
  - it runs every 10 minutes
- Mark [#5836](https://github.com/o/r/pull/5836) ready

### Next

- the follow-up
"""


def test_a_working_brief_gets_no_reminder():
    assert nudge.note(_BLOCKED.replace("blocked", "working")) == ""
    assert nudge.after_answer(_BLOCKED.replace("blocked", "working"), "x") == ""


def test_the_reminder_names_each_needs_label():
    assert nudge.note(_BLOCKED) == (
        'Your brief\'s Status is `blocked`, on: "render timeouts owner", '
        '"Mark [#5836](https://github.com/o/r/pull/5836) ready". If this turn answers or '
        "changes any of these, update Status before ending; otherwise ignore this."
    )


def test_merge_alert_and_approve_wait_on_peter_too():
    assert "`merge`" in nudge.note(_BLOCKED.replace("blocked", "merge"))
    assert "`alert`" in nudge.note(_BLOCKED.replace("blocked", "alert"))
    assert "`approve`" in nudge.note(_BLOCKED.replace("blocked", "approve"))


def test_an_answer_lists_what_is_still_asked():
    assert nudge.after_answer(_BLOCKED, "Render timeouts owner") == (
        'This answers "Render timeouts owner". Your brief says `blocked` on: '
        '"Mark [#5836](https://github.com/o/r/pull/5836) ready". Update Status if that changes.'
    )


def test_an_answer_to_the_last_ask_says_nothing_else_is_asked():
    only = _BLOCKED.replace("- Mark [#5836](https://github.com/o/r/pull/5836) ready\n", "")

    assert nudge.after_answer(only, "render timeouts owner") == (
        'This answers "render timeouts owner". Your brief says `blocked` with nothing else '
        "under Needs Peter. Update Status if that changes."
    )


def test_the_brief_view_appends_the_reminder_to_its_answer(tmp_path):
    path = store.briefs_dir() / "ship.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_BLOCKED)

    body = brief_questions.answer(path, "render timeouts owner", "Alex does")

    assert body.startswith("Answer to render timeouts owner: Alex does\n\nThis answers ")
    assert nudge.carries_note(body)
    assert brief_questions.answer(tmp_path / "gone.md", "x", "y") == "Answer to x: y"


def test_code_spans_in_a_label_stay_as_written():
    brief = _BLOCKED.replace(
        "- Mark [#5836]",
        "- `mid_turn_working`  stays *stale*: why?\n- `a  b`: spaced?\n- `a: b` in __bold__\n- Mark [#5836]",
    )

    assert nudge.note(brief).startswith(
        'Your brief\'s Status is `blocked`, on: "render timeouts owner", '
        '"`mid_turn_working` stays stale", "`a  b`", "`a: b` in bold", '
    )


def test_an_answer_matches_a_label_written_without_backticks():
    brief = _BLOCKED.replace("- Mark [#5836]", "- `snake_case` name: which?\n- Mark [#5836]")

    assert '"`snake_case` name"' not in nudge.after_answer(brief, "snake_case name")
    assert '"`snake_case` name"' in nudge.after_answer(brief, "render timeouts owner")
