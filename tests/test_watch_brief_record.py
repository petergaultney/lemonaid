"""Successful watch startup records a restartable command, not an ephemeral process."""

import argparse
import shlex
from concurrent.futures import ThreadPoolExecutor

import pytest

from lemonaid.brief import attached, store, waiters
from lemonaid.inbox import db
from lemonaid.watch import brief_record, briefs_cli, delivery, doc_cli, file_cli, pr_cli


@pytest.fixture
def brief(monkeypatch):
    import datetime

    path = store.create("watching", datetime.date(2026, 10, 8))
    with db.connect() as conn:
        attached.attach(conn, "codex:owner", path)
    monkeypatch.setenv("LEMONAID_CHANNEL", "codex:owner")
    return path


def args(kind, tmp_path, *extra):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    modules = {"doc": doc_cli, "pr": pr_cli, "file": file_cli, "briefs": briefs_cli}
    modules[kind].add_parser(sub)
    target = (
        ["--wait", "12"]
        if kind == "pr"
        else (
            ["--children", "--self"]
            if kind == "briefs"
            else ["--wait", str(tmp_path / "review notes.md")]
        )
    )
    words = [kind, *target, "--me", "Author (X)", "--state-dir", str(tmp_path / kind), *extra]
    parsed = parser.parse_args(words)
    parsed.invocation = ["lemonaid", "watch", *words]
    return parsed


def child_args(tmp_path, parent):
    a = args("briefs", tmp_path)
    a.use_self, a.lemon = False, parent
    a.invocation = [parent if word == "--self" else word for word in a.invocation]
    return a


def test_pr_rearm_replaces_head_and_flags_without_touching_other_commands(brief, tmp_path):
    a = args("pr", tmp_path, "--head", "abcdef0", "--comments", "--once")
    assert brief_record.record(a, "pr", repo="owner/repo") == ""
    before = brief.read_text()
    store.edit(brief, lambda s: waiters.add(s, "sh /tmp/custom.sh"))
    a = args("pr", tmp_path, "--head", "1234567", "--legacy", "Old Author")
    assert brief_record.record(a, "pr", repo="owner/repo") == ""
    assert brief_record.record(a, "pr", repo="owner/repo") == ""
    commands = waiters.commands(brief.read_text())
    assert len(commands) == 2
    command = next(c for c in commands if c.startswith("lemonaid"))
    assert "--head 1234567" in command and "abcdef0" not in command
    assert "--legacy 'Old Author'" in command
    assert "sh /tmp/custom.sh" in commands
    assert before.split("## Waiters")[0] == brief.read_text().split("## Waiters")[0]


def test_relative_paths_and_bare_codex_thread_are_preserved(brief, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_THREAD_ID", "owner")
    a = args(
        "doc", tmp_path, "--wait", "relative doc.md", "--codex-thread", "--no-edits", "--quiet", "0"
    )
    thread, error = delivery.codex_thread(a.codex_thread)
    assert not error
    assert brief_record.record(a, "doc", thread) == ""
    words = shlex.split(waiters.commands(brief.read_text())[0])
    assert words == a.invocation
    assert "relative doc.md" in words
    assert words[words.index("--codex-thread") + 1] == "--no-edits"
    assert "--no-edits" in words
    assert words[words.index("--quiet") + 1] == "0"


def test_signatures_targets_and_repositories_stay_separate(brief, tmp_path):
    a = args("pr", tmp_path)
    for repo, number, me in [
        ("o/a", 12, "A"),
        ("o/b", 12, "A"),
        ("o/a", 13, "A"),
        ("o/a", 12, "B"),
    ]:
        a = args("pr", tmp_path, "--wait", str(number), "--repo", repo, "--me", me)
        assert brief_record.record(a, "pr", repo=repo) == ""
    assert len(waiters.commands(brief.read_text())) == 4


def test_ordinary_watch_without_attached_brief_records_nothing(tmp_path):
    assert brief_record.record(args("doc", tmp_path), "doc") == ""
    assert not store.briefs_dir().exists()


@pytest.mark.parametrize("kind", ["doc", "pr", "file", "briefs"])
def test_cli_registers_before_waiting_and_keeps_entry_after_one_shot(
    brief, tmp_path, monkeypatch, kind
):
    a = args(kind, tmp_path, "--once")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lemon_identities (path, lemon_id) VALUES (?, ?)",
            (str(brief), "watching.QuickOdd"),
        )
        conn.commit()
    # Keep the file ID consistent with the registration used for child-self resolution.
    text = brief.read_text()
    import re

    brief.write_text(re.sub(r"Brief-ID: .*", "Brief-ID: watching.QuickOdd", text))

    def done(*unused, **unused_keywords):
        assert len(waiters.commands(brief.read_text())) == 1

    if kind == "doc":
        monkeypatch.setattr(doc_cli.doc_wait, "wait_doc", done)
        result = doc_cli.run(a)
    elif kind == "pr":
        monkeypatch.setattr(pr_cli.pr_wait, "wait", done)
        result = pr_cli.run(a, "o/r")
    elif kind == "file":
        monkeypatch.setattr(file_cli, "_wait", done)
        result = file_cli.run(a)
    else:
        monkeypatch.setattr(briefs_cli, "_wait", done)
        result = briefs_cli.run(a)
    assert result == 0
    command = waiters.commands(brief.read_text())[0]
    assert "--once" in command
    if kind == "briefs":
        assert command.startswith("lemonaid watch briefs --children --self")


@pytest.mark.parametrize("codex", [False, True])
def test_pr_ci_startup_and_rearm_record_the_supplied_flags(brief, tmp_path, monkeypatch, codex):
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    mode = ["--codex-thread", "owner"] if codex else ["--once"]
    for head, ci in [("abcdef0", True), ("1234567", True), ("1234567", False)]:
        a = args("pr", tmp_path, "--head", head, "--comments", *mode, *(["--ci"] if ci else []))

        def done(*unused, expected_ci=ci, invocation=a.invocation, **options):
            assert options["ci"] is expected_ci
            assert waiters.commands(brief.read_text()) == [shlex.join(invocation)]

        monkeypatch.setattr(pr_cli.pr_wait, "wait", done)
        assert pr_cli.run(a, "o/r") == 0
        words = shlex.split(waiters.commands(brief.read_text())[0])
        assert ("--ci" in words) is ci
        assert words[words.index("--head") + 1] == head


def test_refused_delivery_setup_and_duplicate_do_not_change_brief(brief, tmp_path, monkeypatch):
    a = args("doc", tmp_path, "--codex-thread", "owner")
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "queue unavailable")
    before = brief.read_text()
    assert doc_cli.run(a) == 2
    assert brief.read_text() == before
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    from lemonaid.watch import doc_events, waiter_lock

    lock = waiter_lock.acquire(
        doc_events.state_stem(a.state_dir, a.wait, a.me).with_suffix(".lock")
    )
    try:
        assert doc_cli.run(a) == 3
        assert brief.read_text() == before
    finally:
        lock.close()


def test_unwritable_attached_brief_prevents_startup(brief, tmp_path, monkeypatch):
    def fail(*args):
        raise PermissionError("brief is read-only")

    monkeypatch.setattr(store, "_replace", fail)
    monkeypatch.setattr(doc_cli.doc_wait, "wait_doc", lambda *a: pytest.fail("must not start"))
    assert doc_cli.run(args("doc", tmp_path)) == 2
    assert "## Waiters" not in brief.read_text()


def test_parallel_watch_starts_preserve_both_entries(brief, tmp_path):
    a, b = args("pr", tmp_path), args("file", tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda item: brief_record.record(*item), [(a, "pr", "", "o/r"), (b, "file")])
        )
    assert results == ["", ""]
    assert len(waiters.commands(brief.read_text())) == 2


def test_upsert_does_not_match_command_prefixes_or_code_examples():
    text = "# task\n\n## Waiters\n- `watch`\n- `watch longer`\n\n```sh\n- `watch`\n```\n"
    out = waiters.upsert(text, "new", lambda old: old == "watch")
    assert waiters.commands(out) == ["new", "watch longer"]
    assert "```sh\n- `watch`" in out


def test_existing_brief_problems_do_not_block_a_watch(brief, tmp_path):
    store.edit(brief, lambda s: store.with_status(s, "nonsense"))
    assert brief_record.record(args("doc", tmp_path), "doc") == ""
    assert "Status: nonsense" in brief.read_text()
    assert len(waiters.commands(brief.read_text())) == 1


def test_status_and_edit_markers_do_not_record(brief, tmp_path):
    a = args("doc", tmp_path)
    a.status, a.wait = a.wait, None
    before = brief.read_text()
    assert doc_cli.run(a) == 1
    assert brief.read_text() == before


def test_saved_child_self_command_and_explicit_defaults_are_replaced(brief, tmp_path):
    store.edit(
        brief, lambda s: waiters.add(s, "lemonaid watch briefs --children --self --me 'Author (X)'")
    )
    a = args("briefs", tmp_path, "--to", "done", "--to", "merge")
    assert brief_record.record(a, "briefs") == ""
    assert len(waiters.commands(brief.read_text())) == 1
    assert "--self" in waiters.commands(brief.read_text())[0]


def test_failed_delivery_keeps_recorded_command_for_rearm(brief, tmp_path, monkeypatch):
    a = args("doc", tmp_path, "--codex-thread", "owner")
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")

    def fail(*args):
        raise delivery.Failed("queue failed")

    monkeypatch.setattr(doc_cli.doc_wait, "wait_doc", fail)
    assert doc_cli.run(a) == 1
    assert len(waiters.commands(brief.read_text())) == 1


def test_explicit_codex_recipient_selects_its_brief(brief, tmp_path):
    import datetime

    other = store.create("other", datetime.date(2026, 10, 8))
    with db.connect() as conn:
        attached.attach(conn, "codex:other", other)
    assert brief_record.record(args("doc", tmp_path), "doc", "other") == ""
    assert waiters.commands(brief.read_text()) == []
    assert len(waiters.commands(other.read_text())) == 1


@pytest.mark.parametrize(
    "suffix", [" && notify-send done", " > /tmp/watch.log", " | tee /tmp/watch.log", ";echo done"]
)
def test_auto_recording_preserves_compound_shell_waiters(brief, tmp_path, suffix):
    custom = "lemonaid watch pr --wait 12 --repo o/r --me 'Author (X)' --once" + suffix
    store.edit(brief, lambda text: waiters.add(text, custom))
    a = args("pr", tmp_path, "--head", "abcdef0")
    assert brief_record.record(a, "pr", repo="o/r") == ""
    commands = waiters.commands(brief.read_text())
    assert custom in commands
    assert len(commands) == 2


def test_child_self_watch_survives_a_different_parent_watch(brief, tmp_path):
    custom = "lemonaid watch briefs --children --self --me 'Author (X)' --once"
    store.edit(brief, lambda text: waiters.add(text, custom))
    assert brief_record.record(child_args(tmp_path, "other.QuickOdd"), "briefs") == ""
    assert custom in waiters.commands(brief.read_text())
    assert len(waiters.commands(brief.read_text())) == 2


def test_child_parent_after_flags_rearms_one_entry(brief, tmp_path):
    old = "lemonaid watch briefs --children parent.QuickOdd --me 'Author (X)' --once"
    store.edit(brief, lambda text: waiters.add(text, old))
    assert brief_record.record(child_args(tmp_path, "parent.QuickOdd"), "briefs") == ""
    commands = waiters.commands(brief.read_text())
    assert len(commands) == 1
    assert "--children parent.QuickOdd" in commands[0]


def test_unknown_child_self_owner_preserves_command():
    old = "lemonaid watch briefs --children --self --me A"
    text = waiters.add("# task\n", old)
    new = "lemonaid watch briefs parent.QuickOdd --children --me A"
    assert waiters.commands(brief_record._upsert(text, new)) == [old, new]


def test_child_watch_records_only_arguments_typed(brief):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    briefs_cli.add_parser(sub)
    words = ["briefs", "--children", "--self", "--once"]
    a = parser.parse_args(words)
    a.invocation = ["lemonaid", "watch", *words]
    assert brief_record.record(a, "briefs") == ""
    assert waiters.commands(brief.read_text()) == ["lemonaid watch briefs --children --self --once"]
    assert brief_record.record(a, "briefs") == ""
    assert len(waiters.commands(brief.read_text())) == 1


def test_main_passes_original_arguments_through_to_recording(brief, tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
    doc = tmp_path / "review notes.md"
    doc.write_text('{{authorId="user" author="User">>Check this.<<}}')
    words = ["watch", "doc", "--wait", str(doc), "--me", "Author (X)", "--once"]
    result = subprocess.run(
        [sys.executable, "-m", "lemonaid", *words],
        capture_output=True,
        text=True,
        env=os.environ,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert waiters.commands(brief.read_text()) == [shlex.join(["lemonaid", *words])]


def test_implicit_repository_context_survives_other_repository_and_rearm(brief, tmp_path):
    first = args("pr", tmp_path, "--head", "abcdef0")
    assert brief_record.record(first, "pr", repo="owner/first") == ""
    second = args("pr", tmp_path, "--repo", "owner/second", "--head", "1234567")
    assert brief_record.record(second, "pr", repo="owner/second") == ""
    assert len(waiters.commands(brief.read_text())) == 2
    rearm = args("pr", tmp_path, "--head", "7654321")
    assert brief_record.record(rearm, "pr", repo="owner/first") == ""
    commands = waiters.commands(brief.read_text())
    assert commands == [shlex.join(rearm.invocation), shlex.join(second.invocation)]


def test_relative_target_context_survives_other_directory_and_rearm(brief, tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    a = args("file", tmp_path, "--wait", "notes.md", "--quiet", "2")
    assert brief_record.record(a, "file") == ""
    monkeypatch.chdir(second)
    b = args("file", tmp_path, "--wait", "notes.md", "--quiet", "5")
    assert brief_record.record(b, "file") == ""
    assert len(waiters.commands(brief.read_text())) == 2
    monkeypatch.chdir(first)
    rearm = args("file", tmp_path, "--wait", "notes.md", "--quiet", "3")
    assert brief_record.record(rearm, "file") == ""
    assert waiters.commands(brief.read_text()) == [
        shlex.join(rearm.invocation),
        shlex.join(b.invocation),
    ]


def test_missing_context_preserves_relative_and_implicit_repository_commands():
    old = "lemonaid watch pr --wait 12 --me A --head abcdef0 --once"
    text = brief_record._upsert("# task\n", old, repo="owner/first")
    new = "lemonaid watch pr --wait 12 --repo owner/second --me A --head 1234567 --once"
    assert waiters.commands(brief_record._upsert(text, new, repo="owner/second")) == [old, new]
    old = "lemonaid watch file --wait notes.md --me A --quiet 2 --once"
    text = brief_record._upsert("# task\n", old)
    new = "lemonaid watch file --wait notes.md --me A --quiet 5 --once"
    assert waiters.commands(brief_record._upsert(text, new)) == [old, new]


def test_same_raw_command_from_multiple_contexts_is_not_replaced(brief, tmp_path):
    a = args("pr", tmp_path, "--head", "abcdef0")
    assert brief_record.record(a, "pr", repo="owner/first") == ""
    assert brief_record.record(a, "pr", repo="owner/second") == ""
    new = args("pr", tmp_path, "--repo", "owner/second", "--head", "1234567")
    assert brief_record.record(new, "pr", repo="owner/second") == ""
    assert waiters.commands(brief.read_text()) == [
        shlex.join(a.invocation),
        shlex.join(new.invocation),
    ]


def test_invalid_context_refuses_registration_without_changing_brief(brief, tmp_path):
    before = brief.read_text()
    brief.with_name(f".{brief.name}.waiter-context.json").write_text('{"command": []}')
    assert "Invalid waiter context" in brief_record.record(args("pr", tmp_path), "pr", repo="o/r")
    assert brief.read_text() == before
