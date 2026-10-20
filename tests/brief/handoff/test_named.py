import argparse
import json
import sqlite3
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from lemonaid import launch_config
from lemonaid.brief import attached
from lemonaid.brief.handoff import cli as handoff_cli
from lemonaid.brief.handoff import executable as handoff_executable
from lemonaid.brief.handoff import launch as handoff_launch
from lemonaid.brief.handoff import report as handoff_report
from lemonaid.brief.handoff import state as handoff_state
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.inbox.migrations import m027_handoff_launch_name


def _args(*argv):
    parser = argparse.ArgumentParser()
    handoff_cli.add_parser(parser.add_subparsers())
    return parser.parse_args(["handoff", *argv])


def test_named_codex_preset_moves_brief_through_request_and_accept(setup, monkeypatch, capsys):
    conn, path = setup
    config = Config(
        tmux_session=TmuxSessionConfig(
            launch=launch_config.Settings(
                presets={
                    "codex-low": launch_config.Preset(
                        "codex", ("--no-daemon", "-c", 'model_reasoning_effort="low"')
                    ),
                }
            )
        )
    )
    for module in (handoff_cli, handoff_launch, handoff_report):
        monkeypatch.setattr(module, "load_config", lambda: config)
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(path.parent))
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.subprocess, "Popen", Mock())
    monkeypatch.setattr(handoff_cli.to_brief, "send", Mock())
    args = _args("--to", "codex-low", "--brief", str(path))
    args.func(args)
    report = json.loads(capsys.readouterr().out)
    token = report["token"]
    row = handoff_state.get(conn, token)
    assert (row["harness"], row["launch_name"]) == ("codex", "codex-low")
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    path.write_text(path.read_text().replace("Old notes.", f"New notes.\nHandoff-Ready: {token}"))
    args = _args("status", token)
    args.func(args)
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "launched"
    assert "--no-daemon -c" in report["start_command"]
    assert 'model_reasoning_effort="low"' in report["start_command"]
    assert not handoff_state.bind_target(conn, token, "claude:wrong")

    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", token)
    args = _args("accept", token)
    args.func(args)
    assert json.loads(capsys.readouterr().out)["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path


def test_migration_keeps_old_handoff_backend_and_is_repeatable():
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE brief_handoffs (harness TEXT)")
        conn.execute("INSERT INTO brief_handoffs VALUES ('codex')")
        m027_handoff_launch_name.migrate(conn)
        m027_handoff_launch_name.migrate(conn)
        assert conn.execute("SELECT harness, launch_name FROM brief_handoffs").fetchall() == [
            ("codex", "")
        ]


def test_handoff_rejects_a_preset_for_an_unsupported_backend(monkeypatch):
    config = Config(
        tmux_session=TmuxSessionConfig(
            launch=launch_config.Settings(
                presets={
                    "other": launch_config.Preset("other-cli"),
                }
            )
        )
    )
    monkeypatch.setattr(handoff_launch, "load_config", lambda: config)
    with pytest.raises(ValueError, match="must run a Claude or Codex"):
        handoff_launch.destination("other")


@pytest.mark.parametrize(
    ("line", "backend"),
    [
        ("lemonaid claude patch && claude --model sonnet --remote-control", "claude"),
        ("lemonaid claude patch && claude --allow-dangerously-skip-permissions", "claude"),
        ("claude", "claude"),
        ("codex --no-daemon", "codex"),
        ("FOO=1 env BAR=2 /usr/bin/codex -c x=1", "codex"),
        ("other-cli --flag", ""),
        ("lemonaid claude patch && other-cli", ""),
        ('echo "&&" claude', ""),
        ("echo ';' codex", ""),
        ("echo \\&\\& claude", ""),
        ('"tools=x/claude" --flag', "claude"),
        ('"FOO=bar" claude', ""),
        ("env -u FOO claude", "claude"),
        ("env -i FOO=1 codex", "codex"),
        ("command -- claude", "claude"),
        ('FOO="a b" claude', "claude"),
        ("/tmp/my\\ tools/claude --x", "claude"),
        ('env "FOO=bar" claude', "claude"),
        ("command -v claude", ""),
        ("command -V claude", ""),
        ("command -pv claude", ""),
        ("command -p claude", "claude"),
        ("env --help claude", ""),
        ("env --version claude", ""),
        ("env --unknown claude", ""),
        ("env --unset=FOO -i claude", "claude"),
        ('env -S "claude --model sonnet"', ""),
        ("lemonaid claude patch && env -u X claude --model sonnet", "claude"),
    ],
)
def test_harness_executable_skips_wrappers(line, backend):
    assert handoff_executable.harness_executable(line) == backend


def test_heal_migration_adds_missing_launch_name_and_is_idempotent():
    from lemonaid.inbox.migrations import m028_heal_handoff_launch_name as m028

    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE brief_handoffs (harness TEXT)")
        conn.execute("INSERT INTO brief_handoffs VALUES ('claude')")
        m028.migrate(conn)
        m028.migrate(conn)
        assert conn.execute("SELECT launch_name FROM brief_handoffs").fetchall() == [("",)]


def test_heal_runs_on_a_database_stuck_at_version_27(tmp_path):
    from lemonaid.inbox import migrations

    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("CREATE TABLE brief_handoffs (harness TEXT)")
    conn.execute("PRAGMA user_version = 27")
    migrations.run_migrations(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(brief_handoffs)")}
    assert "launch_name" in cols
    assert migrations.get_current_version(conn) >= 28
