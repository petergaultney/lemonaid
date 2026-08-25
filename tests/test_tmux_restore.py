"""Planning a rebuild of the tmux layout the inbox describes.

The planning half is pure so the interesting cases - several lemons in one
session, gaps where a non-lemon window was - can be pinned down without a tmux
server.
"""

from lemonaid.config import Config
from lemonaid.inbox.db import Notification
from lemonaid.tmux import restore

_CONFIG = Config()


def _notification(
    channel: str = "claude:abc",
    name: str = "a session",
    session: str | None = "work",
    window: str | None = "2",
    cwd: str = "/tmp/somewhere",
) -> Notification:
    metadata = {"cwd": cwd, "session_id": channel.split(":")[-1]}
    if session is not None:
        metadata["tmux_session"] = session
    if window is not None:
        metadata["tmux_window"] = window

    return Notification(
        id=1, channel=channel, message="", name=name, metadata=metadata, created_at=0.0
    )


def test_plans_one_window_per_session():
    plans = restore.plan_restore([_notification()], _CONFIG)

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
    )

    assert [w.index for w in plans[0].windows] == [1, 5]


def test_separate_sessions_stay_separate():
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", session="relay", window="2"),
            _notification(channel="claude:b", session="main", window="3"),
        ],
        _CONFIG,
    )

    assert [p.name for p in plans] == ["main", "relay"]
    assert all(len(p.windows) == 1 for p in plans)


def test_each_window_keeps_its_own_cwd():
    """One session's lemons routinely sit in different worktrees."""
    plans = restore.plan_restore(
        [
            _notification(channel="claude:a", window="1", cwd="/a"),
            _notification(channel="claude:b", window="2", cwd="/b"),
        ],
        _CONFIG,
    )

    assert [w.cwd for w in plans[0].windows] == ["/a", "/b"]


def test_a_session_with_no_recorded_location_is_skipped():
    """There is nowhere to put it, and inventing a session isn't restoring one."""
    assert restore.plan_restore([_notification(session=None)], _CONFIG) == []


def test_a_window_with_no_recorded_index_is_skipped():
    assert restore.plan_restore([_notification(window=None)], _CONFIG) == []


def test_an_unparseable_window_index_is_skipped():
    assert restore.plan_restore([_notification(window="not-a-number")], _CONFIG) == []


def test_window_zero_is_a_real_index():
    """A base-index of 0 makes window 0 ordinary; it must not read as absent."""
    plans = restore.plan_restore([_notification(window="0")], _CONFIG)

    assert [w.index for w in plans[0].windows] == [0]


def test_a_backend_with_no_resume_command_is_skipped():
    plans = restore.plan_restore([_notification(channel="unknown-backend:x")], _CONFIG)

    assert plans == []


def test_the_resume_command_is_the_backend_s_own():
    plans = restore.plan_restore([_notification(channel="claude:abc123")], _CONFIG)

    assert plans[0].windows[0].argv == ["lemonaid", "claude", "resume", "abc123"]


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
        )
    )

    assert lines[0] == "work"
    assert "2: first" in lines[1]
    assert "3: second" in lines[2]


def test_as_json_carries_what_a_caller_needs_to_act():
    payload = restore.as_json(
        restore.plan_restore([_notification(channel="claude:abc123", window="3")], _CONFIG)
    )

    assert payload == [
        {
            "session": "work",
            "windows": [
                {
                    "index": 3,
                    "cwd": "/tmp/somewhere",
                    "name": "a session",
                    "argv": ["lemonaid", "claude", "resume", "abc123"],
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
    restored, skipped = restore.restore(plans)

    assert not spawned
    assert restored == []
    assert sorted(skipped) == ["hq", "relay"]


def test_a_missing_session_is_still_restored_alongside_running_ones(monkeypatch):
    """Skipping the live ones must not skip the dead one next to them."""
    spawned: list = []
    monkeypatch.setattr(restore, "_existing_sessions", lambda: {"relay"})
    monkeypatch.setattr(restore, "_restore_session", lambda plan: spawned.append(plan.name) or None)

    restored, skipped = restore.restore(
        [
            restore.SessionPlan(name="relay", windows=[]),
            restore.SessionPlan(name="gone", windows=[]),
        ]
    )

    assert spawned == ["gone"]
    assert restored == ["gone"]
    assert skipped == ["relay"]
