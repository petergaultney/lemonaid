"""How `place open` reads its argument.

Inside a root that has a key vocabulary the argument is a key, and a miss means
acquire. Outside every such root no root could have meant it, so it names a
session in the current directory and nothing is acquired. The distinction is
what keeps a mistyped key from silently becoming an empty session.
"""

import argparse
import json
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.brief import attached, identity, store
from lemonaid.config import Config, PlaceRoot, PlacesConfig, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.messages import store as messages_store
from lemonaid.places import cli, lifecycle


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{
            "key": "thing",
            "root": None,
            "detach": False,
            "json": False,
            "harness": "default",
            "prompt": "",
            "no_check": False,
            "brief": "",
            "parent": "",
            "name": "",
            "group": [],
            **kwargs,
        }
    )


def _config(*roots: PlaceRoot) -> Config:
    return Config(
        tmux_session=TmuxSessionConfig(templates={"default": [""]}),
        places=PlacesConfig(roots=list(roots)),
    )


def _records(monkeypatch, config: Config, cwd) -> tuple[list, list]:
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: cwd))

    keyed: list = []
    monkeypatch.setattr(
        lifecycle,
        "open_key",
        lambda key, cfg, root, attach=True, harness="default", prompt="", title="": (
            keyed.append((key, root.path, attach, harness, prompt)),
            (cwd, lifecycle.Opened(key, created=True)),
        )[1],
    )

    sessions: list = []
    monkeypatch.setattr(
        lifecycle,
        "open_session",
        lambda name, directory, cfg, attach=True, harness="default", prompt="", title="": (
            sessions.append((name, directory, attach, harness, prompt)),
            lifecycle.Opened(name, created=True),
        )[1],
    )

    return keyed, sessions


def test_a_key_inside_a_namespaced_root(monkeypatch, tmp_path):
    root = PlaceRoot(path=tmp_path, path_of="wt path {key}", create="wt co {key}")
    keyed, sessions = _records(monkeypatch, _config(root), tmp_path / "sub")

    cli.cmd_open(_args(key="feat/thing"))

    assert keyed == [("feat/thing", tmp_path, True, "default", "")]
    assert not sessions


def test_a_name_outside_every_root(monkeypatch, tmp_path):
    keyed, sessions = _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path, True, "default", "")]
    assert not keyed


def test_a_hookless_root_does_not_claim_the_name(monkeypatch, tmp_path):
    """It has no vocabulary, so being inside it is the same as being outside one."""
    keyed, sessions = _records(monkeypatch, _config(PlaceRoot(path=tmp_path)), tmp_path)

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path, True, "default", "")]
    assert not keyed


def test_the_innermost_root_decides(monkeypatch, tmp_path):
    """A plain clone checked out inside a worktree repo is not part of its namespace."""
    outer = PlaceRoot(path=tmp_path, path_of="wt path {key}")
    inner = PlaceRoot(path=tmp_path / "vendored")
    (tmp_path / "vendored").mkdir()
    keyed, sessions = _records(monkeypatch, _config(outer, inner), tmp_path / "vendored")

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path / "vendored", True, "default", "")]
    assert not keyed


def test_an_explicit_root_is_still_required_to_resolve(monkeypatch, tmp_path, capsys):
    """--root asks for a vocabulary by name; a root without one is an error, not a session."""
    _, sessions = _records(monkeypatch, _config(), tmp_path)

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", root=str(tmp_path)))

    assert not sessions
    assert "No places root configured" in capsys.readouterr().err


def test_detach_is_passed_through(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes", detach=True))

    assert sessions == [("notes", tmp_path, False, "default", "")]


def test_harness_and_prompt_are_passed_through(monkeypatch, tmp_path):
    keyed, _ = _records(
        monkeypatch,
        _config(PlaceRoot(path=tmp_path, path_of="wt path {key}")),
        tmp_path,
    )

    cli.cmd_open(_args(key="feat/thing", harness="codex", prompt="read .z/brief.md"))

    assert keyed == [("feat/thing", tmp_path, True, "codex", "read .z/brief.md")]


def test_json_reports_no_root_for_a_plain_session(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes", json=True))

    assert json.loads(capsys.readouterr().out) == {
        "key": "notes",
        "session": "notes",
        "dir": str(tmp_path),
        "root": None,
        "brief": None,
        "lemon_id": None,
        "parent": None,
        "groups": [],
        "error": None,
    }


def _acquire_args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**{"key": "thing", "root": None, "json": False, **kwargs})


def test_acquire_prints_the_directory(monkeypatch, tmp_path, capsys):
    root = PlaceRoot(path=tmp_path, path_of="echo x")
    monkeypatch.setattr(cli, "load_config", lambda: _config(root))
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(lifecycle, "acquire_key", lambda key, r: (tmp_path / key, None))

    cli.cmd_acquire(_acquire_args(key="feat/thing"))

    assert capsys.readouterr().out.strip() == str(tmp_path / "feat/thing")


def test_acquire_outside_a_namespaced_root_is_an_error(monkeypatch, tmp_path, capsys):
    """There is no key vocabulary here, so nothing could be acquired."""
    monkeypatch.setattr(cli, "load_config", lambda: _config())
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))

    with pytest.raises(SystemExit):
        cli.cmd_acquire(_acquire_args(key="notes"))

    assert "no directory to acquire" in capsys.readouterr().err


def test_acquire_exits_nonzero_on_failure(monkeypatch, tmp_path, capsys):
    root = PlaceRoot(path=tmp_path, path_of="echo x")
    monkeypatch.setattr(cli, "load_config", lambda: _config(root))
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(lifecycle, "acquire_key", lambda key, r: (None, "no create command"))

    with pytest.raises(SystemExit):
        cli.cmd_acquire(_acquire_args(key="nope", json=True))

    assert json.loads(capsys.readouterr().out)["error"] == "no create command"


def test_a_brief_waits_on_the_new_sessions_harness_window(monkeypatch, tmp_path):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    brief_file = store.briefs_dir() / "task.md"
    brief_file.parent.mkdir(parents=True)
    brief_file.write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task"))

    with db.connect() as conn:
        [waiting] = attached.everything(conn)
    assert (waiting.path, waiting.tmux_session, waiting.tmux_window) == (
        brief_file.resolve(),
        "notes",
        "2",
    )


def test_a_brief_without_a_prompt_sends_the_default_first_prompt(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)
    brief_file = store.briefs_dir() / "task.md"
    brief_file.parent.mkdir(parents=True)
    brief_file.write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task"))

    assert (
        sessions[0][-1]
        == f"task. Your task file is {brief_file.resolve()}; read it all and do the work."
    )


def test_the_default_prompt_gets_the_startup_dialog_check(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(cli, "_harness_window", lambda config, harness, session: ("0", "@1"))
    monkeypatch.setattr(cli.launch.window, "startup_dialog", lambda window_id: "a trust dialog")
    brief_file = store.briefs_dir() / "task.md"
    brief_file.parent.mkdir(parents=True)
    brief_file.write_text("# task\n\nStatus: working\n")

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", brief="task"))

    assert "waiting at a trust dialog" in capsys.readouterr().err


def test_an_explicit_prompt_wins_over_the_default(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)
    brief_file = store.briefs_dir() / "task.md"
    brief_file.parent.mkdir(parents=True)
    brief_file.write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", prompt="do it differently"))

    assert sessions[0][-1] == "do it differently"


def test_a_missing_brief_is_refused_before_opening(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", brief="nosuch"))

    assert not sessions


def _parent_brief(channel: str) -> str:
    path = store.briefs_dir() / "parent.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# parent\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def test_parent_self_links_the_briefs_lemon_to_the_caller(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")
    parent = _parent_brief("claude:parent")
    child_brief = store.briefs_dir() / "task.md"
    child_brief.write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", parent="self", json=True))

    opened = json.loads(capsys.readouterr().out)
    assert opened["parent"] == parent
    assert opened["lemon_id"] == identity.from_path(child_brief)
    with db.connect() as conn:
        assert links.parent_of(conn, opened["lemon_id"]) == parent


def _lead_and_author(monkeypatch) -> tuple[str, str]:
    """(lead, author) Lemon-IDs: the caller is the author, a child of the lead."""
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:author")
    lead_path = store.briefs_dir() / "lead.md"
    lead_path.parent.mkdir(parents=True, exist_ok=True)
    lead_path.write_text("# lead\n\nStatus: working\n")
    with db.connect() as conn:
        lead = identity.ensure(conn, lead_path)
    author = _parent_brief("claude:author")
    with db.connect() as conn:
        links.set_parent(conn, author, lead)
    return lead, author


def test_parent_parent_makes_the_reviewer_a_sibling_and_tells_the_parent(
    monkeypatch, tmp_path, capsys
):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    lead, author = _lead_and_author(monkeypatch)
    review = store.briefs_dir() / "review.md"
    review.write_text("# review\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="review", parent="parent", name="Review x", json=True))

    opened = json.loads(capsys.readouterr().out)
    assert opened["parent"] == lead
    with db.connect() as conn:
        assert links.parent_of(conn, opened["lemon_id"]) == lead
    sent = [path.read_text() for path in messages_store.inbox_for_id(lead).iterdir()]
    assert len(sent) == 1
    assert author in sent[0] and "Review x" in sent[0] and str(review) in sent[0]


def _inbox_lines(lemon: str) -> list[str]:
    inbox = messages_store.inbox_for_id(lemon)
    return [path.read_text() for path in inbox.iterdir()] if inbox.exists() else []


def test_parent_self_tells_no_one(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    lead, _ = _lead_and_author(monkeypatch)
    (store.briefs_dir() / "task.md").write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", parent="self", json=True))

    assert _inbox_lines(lead) == []


def test_a_named_parent_is_told_who_started_its_child(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    lead, author = _lead_and_author(monkeypatch)
    (store.briefs_dir() / "task.md").write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", parent=lead, json=True))

    assert [author in line for line in _inbox_lines(lead)] == [True]


def test_a_caller_without_a_brief_gets_no_link_for_parent_parent(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:nobrief")
    store.briefs_dir().mkdir(parents=True, exist_ok=True)
    (store.briefs_dir() / "task.md").write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", parent="parent", json=True))

    assert json.loads(capsys.readouterr().out)["parent"] is None


def test_a_caller_without_a_brief_is_announced_as_someone(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:nobrief")
    store.briefs_dir().mkdir(parents=True, exist_ok=True)
    lead_path = store.briefs_dir() / "lead.md"
    lead_path.write_text("# lead\n\nStatus: working\n")
    (store.briefs_dir() / "task.md").write_text("# task\n\nStatus: working\n")
    with db.connect() as conn:
        lead = identity.ensure(conn, lead_path)

    cli.cmd_open(_args(key="notes", brief="task", parent=lead, json=True))

    assert [line.count("someone started") for line in _inbox_lines(lead)] == [1]


def test_a_failed_announcement_leaves_the_link_and_groups(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    lead, _ = _lead_and_author(monkeypatch)
    (store.briefs_dir() / "task.md").write_text("# task\n\nStatus: working\n")

    def refuse(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(messages_store, "send", refuse)

    cli.cmd_open(_args(key="notes", brief="task", parent="parent", json=True))

    opened = json.loads(capsys.readouterr().out)
    with db.connect() as conn:
        assert links.parent_of(conn, opened["lemon_id"]) == lead


def test_parent_parent_without_a_parent_records_no_link(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")
    _parent_brief("claude:parent")
    child_brief = store.briefs_dir() / "task.md"
    child_brief.write_text("# task\n\nStatus: working\n")

    cli.cmd_open(_args(key="notes", brief="task", parent="parent", json=True))

    opened = json.loads(capsys.readouterr().out)
    assert opened["parent"] is None
    with db.connect() as conn:
        assert links.parent_of(conn, identity.from_path(child_brief)) == ""


def test_a_parent_that_cannot_be_resolved_is_refused_before_opening(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:no-brief")
    child_brief = store.briefs_dir() / "task.md"
    child_brief.parent.mkdir(parents=True)
    child_brief.write_text("# task\n\nStatus: working\n")

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", brief="task", parent="self"))

    assert not sessions


def test_group_puts_the_briefs_lemon_in_an_existing_group(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    child_brief = store.briefs_dir() / "task.md"
    child_brief.parent.mkdir(parents=True)
    child_brief.write_text("# task\n\nStatus: working\n")
    with db.connect() as conn:
        groups.store.create(conn, "Inbox work")

    cli.cmd_open(_args(key="notes", brief="task", group=["Inbox work"], json=True))

    opened = json.loads(capsys.readouterr().out)
    assert opened["groups"] == ["Inbox work"]
    with db.connect() as conn:
        assert groups.store.find(conn, "Inbox work").members == (identity.from_path(child_brief),)


def test_a_missing_group_is_refused_before_opening(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)
    child_brief = store.briefs_dir() / "task.md"
    child_brief.parent.mkdir(parents=True)
    child_brief.write_text("# task\n\nStatus: working\n")

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", brief="task", group=["Nope"]))

    assert not sessions


def _child_of_a_grouped_parent(monkeypatch, tmp_path) -> Path:
    _records(monkeypatch, _config(), tmp_path)
    monkeypatch.setattr(lifecycle, "harness_window", lambda cfg, name: "2")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")
    parent = _parent_brief("claude:parent")
    child_brief = store.briefs_dir() / "task.md"
    child_brief.write_text("# task\n\nStatus: working\n")
    with db.connect() as conn:
        groups.store.create(conn, "Other")
        groups.store.add(conn, groups.store.create(conn, "Inbox work"), [parent])
    return child_brief


def test_a_child_joins_its_parents_groups(monkeypatch, tmp_path, capsys):
    child_brief = _child_of_a_grouped_parent(monkeypatch, tmp_path)

    cli.cmd_open(_args(key="notes", brief="task", parent="self", json=True))

    assert json.loads(capsys.readouterr().out)["groups"] == ["Inbox work"]
    with db.connect() as conn:
        assert identity.from_path(child_brief) in groups.store.find(conn, "Inbox work").members


def test_a_childs_own_group_replaces_its_parents(monkeypatch, tmp_path, capsys):
    _child_of_a_grouped_parent(monkeypatch, tmp_path)

    cli.cmd_open(_args(key="notes", brief="task", parent="self", group=["Other"], json=True))

    assert json.loads(capsys.readouterr().out)["groups"] == ["Other"]


def _dialog_checks(monkeypatch, created: bool) -> list[str]:
    monkeypatch.setattr(
        lifecycle,
        "open_session",
        lambda name,
        directory,
        cfg,
        attach=True,
        harness="default",
        prompt="",
        title="": lifecycle.Opened(name, created=created),
    )
    monkeypatch.setattr(cli.brief.session, "window", lambda session, index: (index, "@9"))
    checked: list[str] = []
    monkeypatch.setattr(
        cli.launch.window,
        "startup_dialog",
        lambda target: checked.append(target) or "Codex's folder-trust prompt",
    )
    return checked


def test_a_new_lemon_stuck_at_a_startup_dialog_is_reported(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)
    checked = _dialog_checks(monkeypatch, created=True)

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", prompt="go", json=True))

    assert checked == ["@9"]
    assert "waiting at Codex's folder-trust prompt" in json.loads(capsys.readouterr().out)["error"]


def test_an_existing_session_is_not_checked_for_a_dialog(monkeypatch, tmp_path):
    """No prompt is sent to a session that already exists, so there is nothing to wait for."""
    _records(monkeypatch, _config(), tmp_path)
    checked = _dialog_checks(monkeypatch, created=False)

    cli.cmd_open(_args(key="notes", prompt="go"))

    assert not checked
