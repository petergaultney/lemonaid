"""`brief check`: what it finds wrong with a brief, and the verbs and Stop hook that use it."""

import argparse
import contextlib
import json

import pytest

from lemonaid.brief import attached, check, identity, store, write_cli
from lemonaid.inbox import db

_BRIEF = """\
# the task

Status: working

Lemon-ID: task.QuickOdd

## Now

### Next

- write the docs

### PRs

| Work | PR | Review |
|---|---|---|
| Brief verbs | [lemonaid#125](https://github.com/o/lemonaid/pull/125) | |

### Done

- parser merged

## Goal
The thing exists.

```bash
# not a heading
## nor this
```

## Waiters
- lemonaid inbox watch --self
"""


def test_a_well_formed_brief_has_no_problems():
    assert check.structure(_BRIEF) == []


def test_every_line_doubled_is_caught():
    doubled = "".join(line + line for line in _BRIEF.splitlines(keepends=True))

    problems = check.structure(doubled)

    assert any("Lemon-ID" in p for p in problems)
    assert any("`## Now` appears 2 times" in p for p in problems)
    assert any("Status" in p for p in problems)


def test_a_second_lemon_id_run_into_the_first_is_caught():
    problems = check.structure(
        _BRIEF.replace("Lemon-ID: task.QuickOdd", "Lemon-ID: task.QuickOddLemon-ID: task.QuickOdd")
    )

    assert problems == ["Brief's Lemon-ID line holds a second Lemon-ID"]


@pytest.mark.parametrize(
    ("before", "after", "found"),
    [
        ("Status: working", "Status: done - PR #12", "is not one word of"),
        ("Status: working\n", "", "No `Status:` line"),
        ("### PRs", "### Needs Peter\n\n- x\n\n### PRs", "out of order"),
        ("- write the docs\n", "", "`### Next` in ## Now is empty"),
        ("|---|---|---|\n", "", "`|---|---|---|`"),
        ("[lemonaid#125](https://github.com/o/lemonaid/pull/125)", "#125", "no pull-request link"),
        ("| Brief verbs |", "| Brief verbs | extra |", "three-column"),
        ("## Goal", "## Waiters\n- x\n\n## Goal", "appears 2 times"),
        ("\n## Waiters\n- lemonaid inbox watch --self\n", "", ""),
        ("### Next\n\n", "### Next\n", "needs a blank line around it"),
        ("| |\n\n### Done", "| |\n### Done", "`### Done` in ## Now needs a blank line"),
        (
            "| Brief verbs | [lemonaid#125](https://github.com/o/lemonaid/pull/125) | |\n",
            "",
            "no rows",
        ),
    ],
)
def test_each_problem_is_named(before, after, found):
    problems = check.structure(_BRIEF.replace(before, after, 1))

    assert any(found in p for p in problems) if found else problems == []


def test_waiters_must_be_last():
    problems = check.structure(_BRIEF + "\n## Notes\nlate\n")

    assert problems == ["`## Waiters` is not the last section"]


def _registered(text: str = _BRIEF):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    with db.connect() as conn:
        identity.ensure(conn, path)
    return path


def test_a_lemon_id_the_database_does_not_record_for_the_brief_is_caught():
    path = _registered()

    with db.connect() as conn:
        problems = check.recorded(conn, path, _BRIEF.replace("QuickOdd", "SlowEven"))

    assert problems == ["Lemon-ID is task.SlowEven, but this brief is task.QuickOdd"]


def _run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args([*argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def _attached(text: str = _BRIEF):
    path = _registered(text)
    with db.connect() as conn:
        db.add(conn, "codex:t1", "", metadata={"tmux_session": "work", "tmux_window": "2"})
        attached.attach(conn, "codex:t1", path)
    return path


def test_check_reports_by_lemon_and_by_file(capsys):
    path = _attached(_BRIEF.replace("Status: working", "Status: busy"))

    by_lemon = _run(capsys, "check", "--channel", "codex:t1")
    by_file = _run(capsys, "check", str(path))

    assert by_lemon["problems"] == by_file["problems"]
    assert "Status 'busy'" in by_lemon["problems"][0]


def test_the_verbs_edit_the_attached_brief(capsys):
    path = _attached()

    _run(capsys, "bullet", "add", "--channel", "codex:t1", "Needs Peter", "merge #125")
    _run(capsys, "bullet", "set", "--channel", "codex:t1", "write", "docs written")
    _run(capsys, "pr", "rm", "--channel", "codex:t1", "125")
    result = _run(
        capsys, "pr", "add", "--channel", "codex:t1", "https://github.com/o/r/pull/7", "Fix"
    )

    text = path.read_text()
    assert result["error"] is None
    assert "### Needs Peter\n\n- merge #125\n" in text
    assert "- docs written\n" in text
    assert "| Fix | [r#7](https://github.com/o/r/pull/7) | |" in text
    assert "lemonaid#125" not in text
    assert check.structure(text) == []


def test_an_edit_that_would_break_the_brief_is_refused(capsys):
    path = _attached()

    refused = _run(capsys, "now", "--channel", "codex:t1", "- x\n\n## Goal\nagain")

    assert "Refused" in refused["error"] and "`## Goal` appears 2 times" in refused["error"]
    assert path.read_text() == _BRIEF


def test_a_brief_that_already_fails_takes_only_the_edit_that_fixes_it(capsys):
    path = _attached(_BRIEF.replace("Status: working", "Status: done - PR #12"))

    refused = _run(capsys, "bullet", "add", "--channel", "codex:t1", "Next", "more")
    fixed = _run(capsys, "status", "--channel", "codex:t1", "done")

    assert "is not one word of" in refused["error"]
    assert fixed["error"] is None
    assert "Status: done\n" in path.read_text() and "- more" not in path.read_text()


def test_now_lays_out_what_it_is_given(capsys):
    path = _attached()

    _run(capsys, "now", "--channel", "codex:t1", "### Done\n- x\n### Next\n- y\n### Running")

    assert "## Now\n\n### Next\n\n- y\n\n### Done\n\n- x\n\n## Goal" in path.read_text()


def test_a_review_doc_in_a_vault_becomes_an_obsidian_link(capsys, monkeypatch, tmp_path):
    vault = tmp_path / "trove"
    (vault / "reviews").mkdir(parents=True)
    (vault / "reviews" / "r-7.md").write_text("")
    config = tmp_path / "config.toml"
    config.write_text(f'[brief]\nvaults = ["{vault}"]\n')
    monkeypatch.setenv("LEMONAID_CONFIG", str(config))
    path = _attached()

    _run(
        capsys,
        "pr",
        "add",
        "--channel",
        "codex:t1",
        "https://github.com/o/r/pull/7",
        "Fix",
        "--review",
        str(vault / "reviews" / "r-7.md"),
    )
    refused = _run(capsys, "pr", "add", "--channel", "codex:t1", "7", "Fix")

    assert "[review doc](obsidian://open?vault=trove&file=reviews%2Fr-7)" in path.read_text()
    assert "pr_url" in refused["error"]
