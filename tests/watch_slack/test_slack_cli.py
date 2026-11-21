"""`lemonaid watch slack` run in the foreground, without the lemon's watcher."""

import argparse

from lemonaid.slack import api, session, signed_out
from lemonaid.slack_config import SlackConfig
from lemonaid.watch import cursors, slack_cli, slack_events, wait_state

from ..slack.shared import LINK, SESSION, THREAD, Slack, reply


def _args(*words: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    slack_cli.add_parser(parser.add_subparsers())
    return parser.parse_args(["slack", *words])


def test_without_a_sign_in_it_stops_and_leaves_the_lemons_notice_to_its_watcher(
    monkeypatch, capsys
):
    monkeypatch.setattr(session, "load", lambda: None)

    assert slack_cli.run(_args(LINK)) == 1

    printed = capsys.readouterr().out
    assert printed.startswith("stopped: Slack is not signed in for your lemons: ask your user")
    directory = cursors.directory("slack", "")
    heard: list[str] = []
    watcher = slack_events.poller(
        THREAD,
        "",
        "",
        False,
        directory,
        "",
        heard.append,
        lambda problem: signed_out.tell_once(directory.parent, problem, heard.append),
        SlackConfig(),
    )
    watcher()
    assert len(heard) == 1 and "lemonaid slack signin" in heard[0]


def test_it_hands_over_once_the_lemons_watcher_starts(monkeypatch, capsys):
    monkeypatch.setattr(api, "call", Slack(replies=[reply("1794857980.000001", "a reply")]))
    monkeypatch.setattr(session, "load", lambda: SESSION)
    monkeypatch.setattr(cursors, "owner", lambda me, codex_thread="": "lemon.Ann")
    monkeypatch.setattr(slack_cli, "_EVERY", 0)
    armed = iter([False, False, True])
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon_id, grace=0: next(armed))

    assert slack_cli.run(_args(LINK)) == 0

    assert "running; it follows this thread from your brief's ## Watching" in (
        capsys.readouterr().out
    )


def test_a_watcher_starting_mid_fetch_still_gets_each_message_the_foreground_printed(
    monkeypatch, capsys
):
    old, new = "1794857980.000001", "1794857990.000002"
    slack = Slack(replies=[reply(old, "an old reply"), reply(new, "a new reply")])
    monkeypatch.setattr(api, "call", slack)
    monkeypatch.setattr(session, "load", lambda: SESSION)
    monkeypatch.setattr(cursors, "owner", lambda me, codex_thread="": "lemon.Ann")
    armed = iter([False, True])  # the watcher arms while the foreground fetches
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon_id, grace=0: next(armed))
    directory = cursors.directory("slack", "")
    directory.mkdir(parents=True)
    cursors.write_json(
        directory / f"{THREAD.channel}-{THREAD.ts}.json", {"cursor": old, "latest": old}
    )

    assert slack_cli.run(_args(LINK, "--after", old)) == 0
    assert "a new reply" in capsys.readouterr().out

    heard: list[str] = []
    watcher = slack_events.poller(
        THREAD, "", "", False, directory, "lemon.Ann", heard.append, heard.append, SlackConfig()
    )
    watcher()
    assert len(heard) == 1 and "a new reply" in heard[0] and "an old reply" not in heard[0]
