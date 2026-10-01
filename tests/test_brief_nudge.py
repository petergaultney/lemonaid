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


def test_merge_and_alert_wait_on_peter_too():
    assert "`merge`" in nudge.note(_BLOCKED.replace("blocked", "merge"))
    assert "`alert`" in nudge.note(_BLOCKED.replace("blocked", "alert"))


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
