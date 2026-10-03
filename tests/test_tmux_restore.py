"""Planning a rebuild of the tmux layout the inbox describes.

The planning half is pure so the interesting cases - several lemons in one
session, gaps where a non-lemon window was - can be pinned down without a tmux
server.
"""

import subprocess

from lemonaid.config import Config
from lemonaid.inbox.db import Notification
from lemonaid.tmux import restore

_CONFIG = Config()
_PLACED = restore.report.Placed("claude:a", "a", "gone:2", "no brief")


def _notification(
    channel: str = "claude:abc",
    name: str = "a session",
    session: str | None = "work",
    window: str | None = "2",
    cwd: str = "/tmp/somewhere",
    order: list[int] | None = None,
) -> Notification:
    metadata: dict = {"cwd": cwd, "session_id": channel.split(":")[-1]}
    if order is not None:
        metadata["tmux_session_order"] = order
    if session is not None:
        metadata["tmux_session"] = session
    if window is not None:
        metadata["tmux_window"] = window

    return Notification(
        id=1, channel=channel, message="", name=name, metadata=metadata, created_at=0.0
    )


def test_plans_one_window_per_session():
    plans = restore.plan_restore([_notification()], _CONFIG, {})

    assert [p.name for p in plans] == ["work"]
    assert [w.index for w in plans[0].windows] == [2]
    assert plans[0].windows[0].cwd == "/tmp/somewhere"


def test_groups_several_lemons_into_one_session():
    """The case this exists for: a crashed session holding five lemons."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", window="2"),
            _notification(channel="claude:b", window="3"),
            _notification(channel="claude:c", window="4"),
        ],
        _CONFIG,
        {},
    )

    assert len(plans) == 1
    assert [w.index for w in plans[0].windows] == [2, 3, 4]


def test_windows_are_ordered_by_index_not_inbox_order():
    plans = restore.plan_restore(
        [
            _notification(channel="claude:c", window="6"),
            _notification(channel="claude:a", window="2"),
            _notification(channel="claude:b", window="4"),
        ],
        _CONFIG,
        {},
    )

    assert [w.index for w in plans[0].windows] == [2, 4, 6]


def test_gaps_between_windows_are_preserved():
    """A window lemonaid knows nothing about must not shift the others down."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", window="1"),
            _notification(channel="claude:b", window="5"),
        ],
        _CONFIG,
        {},
    )

    assert [w.index for w in plans[0].windows] == [1, 5]


def test_separate_sessions_stay_separate():
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="relay", window="2"),
            _notification(channel="claude:b", session="main", window="3"),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["main", "relay"]
    assert all(len(p.windows) == 1 for p in plans)


def test_sessions_come_back_in_the_order_tmux_made_them():
    """Not by name: a listing by index or creation should look as it did."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="alpha", order=[1700000300, 1700000000, 9]),
            _notification(channel="claude:b", session="zulu", order=[1700000100, 1700000000, 2]),
            _notification(channel="claude:c", session="mike", order=[1700000200, 1700000000, 5]),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["zulu", "mike", "alpha"]


def test_sessions_made_in_the_same_second_are_ordered_by_id():
    """A restore makes many sessions at once, so the next restore sees ties."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="alpha", order=[1700000000, 1690000000, 4]),
            _notification(channel="claude:b", session="zulu", order=[1700000000, 1690000000, 3]),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["zulu", "alpha"]


def test_a_same_second_tie_across_servers_goes_to_the_older_server():
    """Ids start again at $0 in each server, so a later server's id can be lower."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="later", order=[1700000000, 1700000000, 0]),
            _notification(channel="claude:b", session="earlier", order=[1700000000, 1690000000, 4]),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["earlier", "later"]


def test_a_session_s_earliest_recorded_order_wins():
    """A lemon whose order was recorded before a later restore still dates the session."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="alpha", window="2", order=[300, 50, 9]),
            _notification(channel="claude:b", session="zulu", order=[200, 50, 2]),
            _notification(channel="claude:c", session="alpha", window="3", order=[100, 50, 1]),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["alpha", "zulu"]
    assert [w.index for w in plans[0].windows] == [2, 3]


def test_sessions_with_no_recorded_order_go_last_by_name():
    """Rows from before the order was recorded must still all come back."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="old-b"),
            _notification(channel="claude:b", session="new", order=[100, 50, 1]),
            _notification(channel="claude:c", session="old-a"),
            _notification(channel="claude:d", session="garbled", order=[100, 1]),
        ],
        _CONFIG,
        {},
    )

    assert [p.name for p in plans] == ["new", "garbled", "old-a", "old-b"]


def test_each_window_keeps_its_own_cwd():
    """One session's lemons routinely sit in different worktrees."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", window="1", cwd="/a"),
            _notification(channel="claude:b", window="2", cwd="/b"),
        ],
        _CONFIG,
        {},
    )

    assert [w.cwd for w in plans[0].windows] == ["/a", "/b"]


def test_a_session_with_no_recorded_location_is_skipped():
    """There is nowhere to put it, and inventing a session isn't restoring one."""
    assert restore.plan_restore([_notification(session=None)], _CONFIG, {}) == []


def test_a_window_with_no_recorded_index_is_skipped():
    assert restore.plan_restore([_notification(window=None)], _CONFIG, {}) == []


def test_an_unparseable_window_index_is_skipped():
    assert restore.plan_restore([_notification(window="not-a-number")], _CONFIG, {}) == []


def test_window_zero_is_a_real_index():
    """A base-index of 0 makes window 0 ordinary; it must not read as absent."""
    plans = restore.plan_restore([_notification(window="0")], _CONFIG, {})

    assert [w.index for w in plans[0].windows] == [0]


def test_a_backend_with_no_resume_command_is_skipped():
    plans = restore.plan_restore([_notification(channel="unknown-backend:x")], _CONFIG, {})

    assert plans == []


def test_the_resume_command_is_the_backend_s_own():
    plans = restore.plan_restore([_notification(channel="claude:abc123")], _CONFIG, {})

    assert plans[0].windows[0].line == "lemonaid claude resume abc123"


def test_describe_says_so_when_there_is_nothing_to_restore():
    assert "Nothing to restore" in restore.describe([])[0]


def test_describe_lists_each_window_under_its_session():
    lines = restore.describe(
        restore.plan_restore(
            [
                _notification(channel="claude:a", name="first", window="2"),
                _notification(channel="claude:b", name="second", window="3"),
            ],
            _CONFIG,
            {},
        )
    )

    assert lines[0] == "work"
    assert "2: first" in lines[1]
    assert "3: second" in lines[2]


def test_as_json_carries_what_a_caller_needs_to_act():
    payload = restore.as_json(
        restore.plan_restore([_notification(channel="claude:abc123", window="3")], _CONFIG, {})
    )

    assert payload == [
        {
            "session": "work",
            "windows": [
                {
                    "index": 3,
                    "cwd": "/tmp/somewhere",
                    "name": "a session",
                    "channel": "claude:abc123",
                    "line": "lemonaid claude resume abc123",
                    "rearm": "no brief",
                }
            ],
        }
    ]


def test_running_it_when_nothing_is_wrong_creates_nothing(monkeypatch):
    """The accident case: every session already exists, so this is a no-op.

    Guarded at the session rather than the window, so an existing session is
    never added to - after a crash you have usually rebuilt some by hand, and
    a half-restored session would put duplicate lemons in your windows.
    """
    spawned: list = []
    monkeypatch.setattr(restore, "_existing_sessions", lambda: {"relay", "hq"})
    monkeypatch.setattr(restore, "_restore_session", lambda plan: spawned.append(plan.name))

    plans = [
        restore.SessionPlan(name="relay", windows=[]),
        restore.SessionPlan(name="hq", windows=[]),
    ]
    done = restore.restore(plans)

    assert not spawned
    assert done.restored == []
    assert sorted(done.skipped) == ["hq", "relay"]


def test_a_missing_session_is_still_restored_alongside_running_ones(monkeypatch):
    """Skipping the live ones must not skip the dead one next to them."""
    spawned: list = []
    monkeypatch.setattr(restore, "_existing_sessions", lambda: {"relay"})
    monkeypatch.setattr(
        restore, "_restore_session", lambda plan: spawned.append(plan.name) or [_PLACED]
    )

    done = restore.restore(
        [
            restore.SessionPlan(name="relay", windows=[]),
            restore.SessionPlan(name="gone", windows=[]),
        ]
    )

    assert spawned == ["gone"]
    assert done.restored == ["gone"]
    assert done.skipped == ["relay"]


def test_a_restored_session_is_built_at_the_client_size(monkeypatch):
    """A detached session with no size is 80x24 and stays there until a client
    shows it. The scratch pane then splits its saved width off an 80-column
    window, leaving the main pane below the minimum - and what you see in the
    slot is the placeholder, a bare `sleep`, which renders as an empty pane."""
    argv: list[list[str]] = []
    monkeypatch.setattr(restore, "_client_size", lambda: ("214", "67"))
    monkeypatch.setattr(restore, "_run", lambda *a: argv.append(list(a)) or True)

    restore._restore_session(
        restore.SessionPlan(
            name="relay",
            windows=[
                restore.Window(
                    index=2,
                    cwd="/tmp",
                    line="claude",
                    environment={},
                    name="a",
                    channel="claude:a",
                    rearm="no brief",
                )
            ],
        )
    )

    new_session = next(c for c in argv if "new-session" in c)
    assert new_session[new_session.index("-x") + 1] == "214"
    assert new_session[new_session.index("-y") + 1] == "67"


def test_no_client_falls_back_to_a_usable_size(monkeypatch):
    """Restoring from a script with no attached client must not produce 80x24."""
    monkeypatch.setattr(
        restore.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""),
    )

    width, height = restore._client_size()
    assert int(width) >= 200
    assert int(height) >= 50


def test_a_lemon_with_a_brief_starts_on_its_rearm_prompt():
    """The prompt goes through the environment, so no shell has to quote it."""
    [plan] = restore.plan_restore(
        [_notification(channel="claude:abc123")], _CONFIG, {"claude:abc123": "rearm `this`"}
    )
    [window] = plan.windows

    assert window.rearm == "prompted"
    assert window.line.endswith('"$LEMONAID_PROMPT"')
    assert window.environment == {"LEMONAID_PROMPT": "rearm `this`"}


def test_a_brief_with_nothing_to_rearm_starts_without_a_prompt():
    [plan] = restore.plan_restore(
        [_notification(channel="claude:abc123")], _CONFIG, {"claude:abc123": ""}
    )
    [window] = plan.windows

    assert window.rearm == "nothing to rearm"
    assert window.environment == {}
    assert "LEMONAID_PROMPT" not in window.line


def test_a_codex_lemon_skips_its_trust_and_update_dialogs():
    [plan] = restore.plan_restore([_notification(channel="codex:t1")], _CONFIG, {})

    assert "check_for_update_on_startup=false" in plan.windows[0].line
    assert 'trust_level="trusted"' in plan.windows[0].line


def test_each_window_is_started_with_its_prompt_in_the_environment(monkeypatch):
    argv: list[list[str]] = []
    monkeypatch.setattr(restore, "_client_size", lambda: ("200", "50"))
    monkeypatch.setattr(restore, "_run", lambda *a: argv.append(list(a)) or True)

    [plan] = restore.plan_restore(
        [
            _notification(channel="claude:a", window="2"),
            _notification(channel="claude:b", window="3"),
        ],
        _CONFIG,
        {"claude:a": "first", "claude:b": "second"},
    )
    placed = restore._restore_session(plan)

    new_session = next(c for c in argv if "new-session" in c)
    new_window = next(c for c in argv if "new-window" in c)
    assert "LEMONAID_PROMPT=first" in new_session
    assert "LEMONAID_PROMPT=second" in new_window
    assert [(p.channel, p.where) for p in placed or []] == [
        ("claude:a", "work:2"),
        ("claude:b", "work:3"),
    ]


def _fail_on(word: str):
    """A `_run` that fails the one tmux command containing *word*."""
    return lambda *a: word not in a


def _plan_of_two() -> restore.SessionPlan:
    [plan] = restore.plan_restore(
        [
            _notification(channel="claude:a", window="2"),
            _notification(channel="claude:b", window="3"),
        ],
        _CONFIG,
        {},
    )
    return plan


def test_a_window_tmux_would_not_create_is_reported_not_restored(monkeypatch):
    monkeypatch.setattr(restore, "_existing_sessions", set)
    monkeypatch.setattr(restore, "_client_size", lambda: ("200", "50"))
    monkeypatch.setattr(restore, "_run", _fail_on("new-window"))

    done = restore.restore([_plan_of_two()])

    assert [p.channel for p in done.placed] == ["claude:a"]
    assert [(f.channel, f.outcome, f.detail) for f in done.failed] == [
        ("claude:b", "not restored", "could not create its window")
    ]
    assert done.restored == ["work"]


def test_a_session_tmux_would_not_create_reports_every_lemon_in_it(monkeypatch):
    monkeypatch.setattr(restore, "_existing_sessions", set)
    monkeypatch.setattr(restore, "_client_size", lambda: ("200", "50"))
    monkeypatch.setattr(restore, "_run", _fail_on("new-session"))

    done = restore.restore([_plan_of_two()])

    assert done.placed == [] and done.restored == []
    assert [f.channel for f in done.failed] == ["claude:a", "claude:b"]


def test_a_line_that_could_not_be_typed_is_not_counted_as_started(monkeypatch):
    monkeypatch.setattr(restore, "_existing_sessions", set)
    monkeypatch.setattr(restore, "_client_size", lambda: ("200", "50"))
    monkeypatch.setattr(restore, "_run", _fail_on("send-keys"))

    done = restore.restore([_plan_of_two()])

    assert done.placed == []
    assert {f.detail for f in done.failed} == {"could not type its line into the window"}


def test_a_harness_that_takes_no_prompt_is_resumed_without_one_and_rearmed_by_hand():
    [plan] = restore.plan_restore(
        [_notification(channel="opencode:s1")], _CONFIG, {"opencode:s1": "rearm these"}
    )
    [window] = plan.windows

    assert window.rearm == "rearm by hand"
    assert window.environment == {}
    assert "LEMONAID_PROMPT" not in window.line
