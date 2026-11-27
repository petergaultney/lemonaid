"""`lemonaid watch slack` run in the foreground, without the lemon's watcher: a watch source's
command, run with the Slack plugin."""

import argparse

from lemonaid.sources import plugin, problems
from lemonaid.watch import cursors, registry, source_cli, source_events, wait_state
from lemonaid_slack import api, session

from ..lemonaid_slack.shared import LINK, SESSION, THREAD, Slack, reply

SLACK = plugin.defaults()[0]


def _args(*words: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source_cli.add_parsers(parser.add_subparsers())
    return parser.parse_args(["slack", *words])


def _run(*words: str) -> int:
    return source_cli._run(SLACK, _args(*words))


def _watcher(directory, lemon_id: str, heard: list) -> source_events.Poller:
    return source_events.Poller(
        SLACK,
        (LINK,),
        THREAD.target,
        False,
        directory,
        lemon_id,
        heard.append,
        lambda problem: problems.tell_once(directory.parent, "slack", problem, heard.append),
    )


def test_without_a_sign_in_it_stops_and_leaves_the_lemons_notice_to_its_watcher(
    monkeypatch, capsys
):
    monkeypatch.setattr(session, "load", lambda: None)

    assert _run(LINK) == 1

    printed = capsys.readouterr().out
    assert printed.startswith("stopped: Slack is not signed in for your lemons: ask your user")
    directory = cursors.directory("slack", "")
    heard: list[str] = []
    _watcher(directory, "", heard)()
    assert len(heard) == 1 and "lemonaid slack signin" in heard[0]


def test_it_hands_over_once_the_lemons_watcher_starts(monkeypatch, capsys):
    monkeypatch.setattr(api, "call", Slack(replies=[reply("1794857980.000001", "a reply")]))
    monkeypatch.setattr(session, "load", lambda: SESSION)
    monkeypatch.setattr(cursors, "owner", lambda me, codex_thread="": "lemon.Ann")
    monkeypatch.setattr(source_cli, "_EVERY", 0)
    armed = iter([False, False, True])
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon_id, grace=0: next(armed))

    assert _run(LINK) == 0

    assert "running; it follows this slack subscription from your brief's ## Watching" in (
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

    assert _run(LINK, "--after", old) == 0
    assert "a new reply" in capsys.readouterr().out

    heard: list[str] = []
    _watcher(directory, "lemon.Ann", heard)()
    assert len(heard) == 1 and "a new reply" in heard[0] and "an old reply" not in heard[0]


def test_while_it_follows_it_is_registered_as_its_lemons_waiter(monkeypatch, capsys):
    monkeypatch.setattr(api, "call", Slack(replies=[reply("1794857980.000001", "a reply")]))
    monkeypatch.setattr(session, "load", lambda: SESSION)
    monkeypatch.setattr(cursors, "owner", lambda me, codex_thread="": "lemon.Ann")
    monkeypatch.setattr(source_cli, "_EVERY", 0)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:ann")
    seen = []

    def armed(lemon_id: str, grace: float = 0) -> bool:
        seen.append([(w.kind, w.channel, w.targets) for w in registry.running()])
        return len(seen) > 1

    monkeypatch.setattr(wait_state, "is_armed", armed)

    assert _run(LINK) == 0

    assert seen == [[], [("slack", "claude:ann", THREAD.target)]]
    assert list(registry.running()) == []


def test_every_word_reaches_the_plugin_whatever_its_order(capsys):
    assert _args("--after", "1794857980.000001", LINK).args == [
        "--after",
        "1794857980.000001",
        LINK,
    ]
    assert _args("--me", "Ann", LINK, "--once").args == ["--me", "Ann", LINK, "--once"]
    assert _run("--help") == 0
    assert capsys.readouterr().out.startswith("usage: lemonaid watch slack [--me NAME]")
