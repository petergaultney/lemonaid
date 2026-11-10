"""The restore drill: kill a tmux server full of lemons and check what comes back.

Each test is one scenario from the restart design, run on the private server and
stand-in lemons of `tmux_world`.
"""

import contextlib
import json
import os
import signal
import subprocess
import time
from collections import abc
from pathlib import Path

from lemonaid.config import load_config
from lemonaid.inbox import db, ended
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.launch.restart import state
from lemonaid.lemon_watchers import watcher
from lemonaid.restore import auto, inbox_report

from .tmux_world import (
    IDS,
    WHERE,
    channel,
    crash,
    inbox_row,
    lemonaid,
    restore_all,
    tmux,
    wait,
    window,
)


@contextlib.contextmanager
def _inbox() -> abc.Iterator[None]:
    """The inbox's watcher, running until the block ends."""
    watcher_hooks.start(load_config(), brief_cards.BriefCache(), lambda channels: None)
    try:
        yield
    finally:
        watcher.stop_unified_watcher()


def _cause(name: str) -> str:
    found = inbox_row(name)
    assert found is not None, name
    return ended.cause(found.metadata)


def _restore() -> dict:
    return json.loads(lemonaid("restore", "--wait", "0", "--json").stdout)


def test_the_inbox_started_on_a_new_server_before_restore_keeps_every_lost_lemon(world):
    crash(world)
    tmux("new-session", "-d", "-s", "fresh")  # the server a person starts first

    with _inbox():
        wait("every lemon to be marked lost", lambda: all(_cause(n) for n in WHERE))
        time.sleep(3)  # more passes, in case one archives them

    for name in WHERE:
        found = inbox_row(name)
        assert found is not None and not found.is_archived, name
        assert _cause(name) == ended.SERVER_LOST, name

    restore_all(world)
    for name in WHERE:
        assert _cause(name) == "", name  # heard from again: lost no longer


def test_restoring_twice_starts_nothing_the_second_time(world):
    crash(world)
    restore_all(world)
    pids = {name: (world.running(name) or {}).get("pid") for name in WHERE}

    again = _restore()

    assert again["restored"] == []
    assert {name: (world.running(name) or {}).get("pid") for name in WHERE} == pids


def test_a_session_killed_on_a_living_server_is_closed_not_lost(world):
    crash(world)
    restore_all(world)
    c = world.running("C")
    assert c is not None
    tmux("kill-session", "-t", "side")
    wait("C to die with its session", lambda: world.running("C") is None)

    with _inbox():
        wait("C to be archived", lambda: (row := inbox_row("C")) and row.is_archived)

    assert _cause("C") == ended.PANE_CLOSED
    assert _restore()["restored"] == []
    assert world.running("C") is None


def test_a_lemon_that_ended_itself_stays_ended(world):
    crash(world)
    restore_all(world)
    a = world.running("A")
    assert a is not None
    subprocess.run(
        ["lemonaid", "claude", "session-end"],
        input=json.dumps({"session_id": IDS["A"], "reason": "prompt_input_exit"}),
        text=True,
        check=True,
    )
    os.kill(a["pid"], signal.SIGKILL)

    with _inbox():
        wait("A to be archived", lambda: (row := inbox_row("A")) and row.is_archived)
    assert _cause("A") == ended.USER_EXIT

    tmux("kill-server")
    assert channel("A") not in {r["channel"] for r in _restore()["lemons"]}
    assert world.running("A") is None


def test_dismissed_lemons_are_archived_and_not_restored(world):
    crash(world)

    dismissed = lemonaid("restore", "dismiss", channel("C"))

    assert dismissed.returncode == 0, dismissed.stderr
    assert _cause("C") == ended.DISMISSED
    found = inbox_row("C")
    assert found is not None and found.is_archived
    restored = _restore()
    assert channel("C") not in {r["channel"] for r in restored["lemons"]}
    assert sorted(restored["restored"]) == sorted(channel(n) for n in ("A", "B", "OLD"))


def test_dismissing_all_leaves_nothing_to_restore(world):
    crash(world)

    assert lemonaid("restore", "dismiss", "--all").returncode == 0

    with db.connect() as conn:
        assert not [row for row in db.get_active(conn) if row.channel.startswith("claude:")]
    assert _restore()["restored"] == []


def test_a_channel_cleared_before_the_loss_is_replaced_and_only_its_successor_restored(world):
    crash(world)  # OLD ran in B's window first
    subprocess.run(
        ["lemonaid", "claude", "session-end"],
        input=json.dumps({"session_id": IDS["OLD"], "reason": "clear"}),
        text=True,
        check=True,
    )

    restored = restore_all(world)

    assert _cause("OLD") == ended.REPLACED
    found = inbox_row("OLD")
    assert found is not None and found.is_archived
    assert channel("OLD") not in {r["channel"] for r in restored["lemons"]}


def test_a_lemon_that_cant_be_pushed_to_is_prompted_to_rearm_its_waiters(world):
    crash(world)
    # A session that can reach bypass-permissions mode could hold a pushed message, so
    # lemonaid starts no scout for it unless its settings accept cross-session messages.
    config = Path(os.environ["LEMONAID_CONFIG"])
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "[backends.claude]\nresume_command = "
        '"lemonaid claude --allow-dangerously-skip-permissions --resume {session_id}"\n'
    )

    restored = restore_all(world, seconds=30)

    assert {r["channel"]: r["outcome"] for r in restored["lemons"]} == {
        channel("A"): "working",
        channel("B"): "working",
        channel("C"): "no brief",
        channel("OLD"): "working",
    }, restored["lemons"]
    for name in ("A", "B", "OLD"):
        assert f"/tmp/{name}.md" in world.typed(name), name
    assert world.typed("C") == ""


def test_a_session_rebuilt_by_hand_gains_only_its_missing_lemons(world):
    crash(world)
    tmux("new-session", "-d", "-s", "work", "-x", "160", "-y", "48")
    tmux("send-keys", "-t", "work:1", f"claude --resume {IDS['A']}", "Enter")
    a = wait("A to be resumed by hand", lambda: world.running("A"))
    tmux("new-window", "-t", "work:2")  # a person's shell, where B used to be
    shell = tmux("display-message", "-p", "-t", "work:2", "#{pane_id}")

    restored = _restore()

    assert channel("A") not in {r["channel"] for r in restored["lemons"]}  # heard from: not lost
    assert (world.running("A") or {}).get("pid") == a["pid"]
    assert tmux("display-message", "-p", "-t", "work:2", "#{pane_id}") == shell
    for name, where in {"B": "work:3", "OLD": "work:4", "C": "side:3"}.items():
        found = wait(f"{name} to be restored", lambda name=name: world.running(name))
        assert window(found["pane"]) == where, name
        row = inbox_row(name)
        assert row is not None
        assert f"{row.metadata['tmux_session']}:{row.metadata['tmux_window']}" == where, name


def test_a_lemon_whose_transcript_is_gone_is_reported_and_nothing_runs_in_its_name(world):
    crash(world)
    for transcript in Path(os.environ["CLAUDE_CONFIG_DIR"]).glob(f"projects/*/{IDS['C']}.jsonl"):
        transcript.unlink()  # its history.jsonl line stays, as it does when one is deleted

    restored = _restore()

    [c] = [r for r in restored["lemons"] if r["channel"] == channel("C")]
    assert (c["outcome"], c["detail"]) == ("not restored", "its conversation's transcript is gone")
    assert world.running("C") is None
    assert "side" not in tmux("list-sessions", "-F", "#{session_name}").split()  # C's only
    assert _cause("C") == ended.SERVER_LOST
    with db.connect() as conn:
        listed = db.get_by_channel(conn, inbox_report.CHANNEL, unread_only=False)
    assert listed is not None and "transcript is gone" in listed.message


def test_a_lemon_comes_back_on_the_model_it_was_started_with(world):
    crash(world)
    state.write(
        f"native-{state.key(channel('A'))}.json",
        {"session_id": IDS["A"], "argv": ["claude", "--model", "haiku", "--session-id", IDS["A"]]},
    )

    restore_all(world)

    argv = (world.running("A") or {}).get("argv", [])
    assert argv[argv.index("--model") + 1] == "haiku"
    assert "--model" not in (world.running("B") or {}).get("argv", [])


def _asked() -> db.Notification | None:
    with db.connect() as conn:
        return db.get_by_channel(conn, auto.ASK_CHANNEL, unread_only=False)


def _auto(setting: str) -> None:
    Path(os.environ["LEMONAID_CONFIG"]).write_text(f'[restore]\nauto = "{setting}"\n')


def test_with_auto_on_the_inbox_restores_lost_lemons_by_itself(world):
    _auto("on")
    crash(world)
    tmux("new-session", "-d", "-s", "fresh")  # the server a person starts first
    before = {name: (world.running(name) or {}).get("pid") for name in WHERE}

    with _inbox():
        for name in WHERE:
            wait(
                f"{name} to be restored",
                lambda name=name: (found := world.running(name)) and found["pid"] != before[name],
                timeout=90,
            )

    wait("the restore to finish", lambda: (row := _asked()) is not None and row.is_archived, 90)
    for name in WHERE:
        assert _cause(name) == "", name


def test_with_auto_on_a_trigger_never_starts_tmux_and_the_lemons_wait_for_it(world):
    _auto("on")
    crash(world)

    waited = lemonaid("restore", "--auto", "--wait", "0", "--json")

    assert waited.returncode == 0, waited.stderr
    assert sorted(json.loads(waited.stdout)["waiting"]) == sorted(
        channel(name) for name in [*WHERE, "OLD"]
    )
    assert subprocess.run(["tmux", "list-sessions"], capture_output=True).returncode != 0
    asked = _asked()
    assert asked is not None and not asked.is_archived
    assert all(_cause(name) == ended.SERVER_LOST for name in WHERE)

    tmux("new-session", "-d", "-s", "fresh")  # the person starts tmux
    restored = lemonaid("restore", "--auto", "--wait", "0", "--json")
    assert sorted(json.loads(restored.stdout)["restored"]) == sorted(
        channel(name) for name in [*WHERE, "OLD"]
    )


def test_with_auto_ask_a_trigger_leaves_one_row_and_starts_nothing(world):
    _auto("ask")
    crash(world)

    first = lemonaid("restore", "--auto")
    second = lemonaid("restore", "--auto")

    assert first.returncode == second.returncode == 0, first.stderr
    assert not any(world.running(name) for name in WHERE)
    with db.connect() as conn:
        asked = [r for r in db.get_active(conn) if r.channel == auto.ASK_CHANNEL]
    assert len(asked) == 1 and asked[0].message.startswith("4 lemons were lost with their terminal")


def test_with_auto_off_a_trigger_does_nothing(world):
    _auto("off")
    crash(world)

    assert lemonaid("restore", "--auto").returncode == 0

    assert not any(world.running(name) for name in WHERE)
    assert _cause("A") == ""  # not even judged


def test_two_triggers_at_once_restore_once(world):
    _auto("on")
    crash(world)
    tmux("new-session", "-d", "-s", "fresh")

    runs = [
        subprocess.Popen(
            ["lemonaid", "restore", "--auto", "--wait", "0", "--json"],
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [run.communicate(timeout=120)[0] for run in runs]

    restored = [
        channel for out in outputs if out.strip() for channel in json.loads(out)["restored"]
    ]
    assert sorted(restored) == sorted(channel(name) for name in [*WHERE, "OLD"])  # each once
    for name in WHERE:
        assert world.running(name) is not None, name
