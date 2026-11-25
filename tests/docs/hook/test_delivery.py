"""The docs hook delivering: to a `packages` lemon everything, and to a `classic` lemon the
packages and triggers that name its group or its lead."""

import io
import json

import pytest

from lemonaid.config import load_config
from lemonaid.docs import compose, deliveries, hook, index, lemons, mode, paths, start

from ..shared import configure, doc

_SESSION = "0f0e0d0c-1111-2222-3333-444455556666"


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "packages/oria.md", {"package-for": [{"group": "oria"}]})
    doc(root, "voice.md", {"package": "core"}, "Write plainly.\n")
    doc(root, "flaky.md", {"package": "oria"}, "Chase every flaky test.\n")
    doc(
        root,
        "prs.md",
        {
            "load-when": [
                {"command": r"^gh pr create\b", "section": "Drafts", "before": True},
                {"command": r"^gh pr view\b"},
            ],
            "reminder": "Open PRs as drafts.",
        },
        "# PRs\n\n## Drafts\n\nOpen as a draft.\n",
    )
    doc(
        root,
        "rerun.md",
        {"load-when": [{"command": r"\bgh run rerun\b", "group": "oria", "before": True}]},
        "Don't rerun a flaky test.\n",
    )
    configure([root])
    index.build([root], paths.index())
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "")
    return root


def _kin(monkeypatch, groups=(), ancestors=()):
    monkeypatch.setattr(lemons, "kin", lambda lemon_id: (tuple(groups), tuple(ancestors)))


def _run(event: str, harness: str = "claude", **fields) -> hook.compose.Outcome:
    data = {"session_id": _SESSION, "hook_event_name": event, "cwd": "/tmp", **fields}
    return hook.outcome(data, harness, load_config())


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.fixture
def packages(monkeypatch):
    monkeypatch.setenv("LEMONAID_DOCS", "packages")


@pytest.mark.usefixtures("root", "packages")
def test_a_codex_packages_lemon_gets_its_packages_at_start_and_after_compaction():
    started = _run("SessionStart", harness="codex", source="startup")

    assert "Write plainly." in started.context and "flaky" not in started.context
    assert _run("SessionStart", harness="codex", source="resume").context == ""
    assert "Write plainly." in _run("SessionStart", harness="codex", source="compact").context


@pytest.mark.usefixtures("root", "packages")
def test_a_claude_lemon_launched_with_its_packages_is_given_them_only_when_they_change(
    monkeypatch, tmp_path
):
    docs = index.read(paths.index())
    manifest, flags = start.write(start.members(docs, ["core"]), {"claudeMdExcludes": ["x"]})
    monkeypatch.setenv(start.START_ENV, str(manifest))

    started = _run("SessionStart", source="startup")

    assert started.context == ""
    assert [e["delivery"] for e in started.entries if e["kind"] == "doc"] == ["launch"]
    assert "Write plainly." in (tmp_path / flags[1]).read_text()
    assert _run("SessionStart", source="compact").context == ""

    (tmp_path / "docs" / "voice.md").write_text("---\npackage: core\n---\nWrite very plainly.\n")
    assert "Write very plainly." in _run("SessionStart", source="compact").context


@pytest.mark.usefixtures("root", "packages")
def test_a_claude_session_cannot_claim_another_s_launch(monkeypatch):
    manifest, _ = start.write([], None)
    monkeypatch.setenv(start.START_ENV, str(manifest))
    assert start.claim("first", "startup")

    assert start.claim("a-claude-p-it-ran", "startup") == {}
    assert start.claim("after-clear", "clear")


@pytest.mark.usefixtures("root", "packages")
def test_a_before_trigger_refuses_once_and_a_plain_one_gives_its_section():
    _run("SessionStart", source="startup")

    refused = _run("PreToolUse", **_bash("gh pr create --fill"))
    assert "Open as a draft." in refused.refusal and refused.context == ""
    assert _run("PreToolUse", **_bash("gh pr create --draft")).refusal == ""
    assert "Open as a draft." in _run("PreToolUse", **_bash("gh pr view 3")).context


@pytest.mark.usefixtures("root", "packages")
def test_the_hook_refuses_with_exit_2_and_delivers_context_as_json(monkeypatch, capsys):
    _run("SessionStart", source="startup")

    def call(command):
        stdin = {"session_id": _SESSION, "hook_event_name": "PreToolUse", **_bash(command)}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin)))
        hook.handle("claude")

    with pytest.raises(SystemExit) as exited:
        call("gh pr create")
    assert exited.value.code == 2 and "refused this call once" in capsys.readouterr().err

    call("gh pr view 1")
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse" and "PRs" in output["additionalContext"]
    assert not any(e["shadow"] for e in deliveries.read() if e["kind"] == "doc")


@pytest.mark.usefixtures("packages")
def test_claude_gets_what_fits_and_the_rest_at_its_next_calls(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    for name in "abc":
        doc(root, f"{name}.md", {"package": "core"}, name * 4_000 + "\n")
    doc(root, "huge.md", {"package": "core"}, "h" * 20_000 + "\n")
    configure([root])
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "")

    started = _run("SessionStart", source="startup")
    first = _run("PreToolUse", **_bash("ls"))
    second = _run("PreToolUse", **_bash("ls"))

    assert all(len(o.context) < 10_000 for o in (started, first, second))
    given = [e for o in (started, first, second) for e in o.entries if e["kind"] == "doc"]
    assert sorted(e["doc"].rsplit("/", 1)[1] for e in given) == ["a.md", "b.md", "c.md", "huge.md"]
    assert {e["delivery"] for e in given if e["doc"].endswith("huge.md")} == {"pointer"}
    assert len(started.context) <= compose.CLAUDE_LIMIT


@pytest.mark.usefixtures("root")
def test_a_classic_lemon_gets_only_its_group_s_package_and_triggers(monkeypatch):
    _kin(monkeypatch, groups=["oria"])

    started = _run("SessionStart", source="startup")
    assert "Chase every flaky test." in started.context
    assert "Write plainly." not in started.context

    assert "Don't rerun" in _run("PreToolUse", **_bash("gh run rerun 5 --failed")).refusal
    viewed = _run("PreToolUse", **_bash("gh pr view 3"))
    assert viewed.context == "" and viewed.entries[0]["shadow"] is True


@pytest.mark.usefixtures("root")
def test_a_lemon_outside_the_group_gets_neither():
    _run("SessionStart", source="startup")

    assert _run("PreToolUse", **_bash("gh run rerun 5")).refusal == ""


@pytest.mark.usefixtures("root")
def test_a_package_joined_mid_session_and_a_doc_new_to_it_arrive_at_the_next_call(
    monkeypatch, root
):
    monkeypatch.setattr(hook, "INDEX_MAX_AGE", 0.0)
    _run("SessionStart", source="startup")
    assert _run("PreToolUse", **_bash("ls")).context == ""

    _kin(monkeypatch, groups=["oria"])
    assert "Chase every flaky test." in _run("PreToolUse", **_bash("ls")).context

    doc(root, "uploads.md", {"package": "oria"}, "Retry uploads twice.\n")
    later = _run("PreToolUse", **_bash("ls"))
    assert "Retry uploads twice." in later.context and "Chase" not in later.context


@pytest.mark.usefixtures("root")
def test_under_reaches_a_lead_s_whole_tree(monkeypatch, root):
    doc(root, "packages/lead.md", {"package-for": [{"under": "MilkyWay"}]})
    doc(root, "lead-rule.md", {"package": "lead"}, "The lead's rule.\n")
    index.build([root], paths.index())
    _kin(monkeypatch, ancestors=["SweetShy.oria-upload", "MilkyWay.oria-lead"])

    assert "The lead's rule." in _run("SessionStart", source="startup").context


@pytest.mark.usefixtures("packages")
def test_a_codex_packages_lemon_no_package_is_for_gets_the_classic_docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/python.md", {"package-for": [{"file": "pyproject.toml"}]})
    (tmp_path / "classic.md").write_text("The whole chain.\n")
    configure([root], f'classic = "{tmp_path / "classic.md"}"\n')
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "")

    assert "The whole chain." in _run("SessionStart", harness="codex", source="startup").context


@pytest.mark.usefixtures("packages")
def test_a_before_prompt_trigger_never_refuses_the_user_s_message(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "merge.md", {"load-when": [{"prompt": "merge", "before": True}]}, "Not you.\n")
    configure([root])
    index.build([root], paths.index())
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "")

    given = _run("UserPromptSubmit", prompt="please merge it")

    assert given.refusal == "" and "Not you." in given.context


@pytest.mark.usefixtures("packages")
def test_a_package_doc_just_over_what_a_response_holds_is_named_not_deferred_forever(
    tmp_path, monkeypatch
):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "near.md", {"package": "core"}, "x" * 9_300 + "\n")
    configure([root])
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "")

    started = _run("SessionStart", source="startup")
    later = _run("PreToolUse", **_bash("ls"))

    assert "x" * 9_300 not in started.context + later.context
    assert "near.md applies" in started.context
    assert _run("PreToolUse", **_bash("ls")).context == ""


@pytest.mark.usefixtures("root")
def test_a_doc_only_logged_still_reaches_a_lemon_that_joins_its_group(monkeypatch, root):
    doc(root, "both.md", {"package": ["core", "oria"]}, "A rule for both.\n")
    index.build([root], paths.index())
    assert "A rule for both." not in _run("SessionStart", source="startup").context

    _kin(monkeypatch, groups=["oria"])

    assert "A rule for both." in _run("PreToolUse", **_bash("ls")).context


@pytest.mark.usefixtures("root")
def test_a_trigger_only_logged_doesn_t_hide_the_same_doc_from_a_group_trigger(monkeypatch, root):
    doc(
        root,
        "team.md",
        {"load-when": [{"command": "^echo shadow"}, {"command": "^echo actual", "group": "oria"}]},
        "A team rule.\n",
    )
    index.build([root], paths.index())
    _kin(monkeypatch, groups=["oria"])
    _run("SessionStart", source="startup")

    assert _run("PreToolUse", **_bash("echo shadow")).context == ""
    assert "A team rule." in _run("PreToolUse", **_bash("echo actual")).context


@pytest.mark.usefixtures("root", "packages")
def test_a_claude_lemon_changed_to_classic_keeps_packages_through_compaction():
    _run("SessionStart", source="startup")
    mode.record("claude", _SESSION, "classic")

    compacted = _run("SessionStart", source="compact")
    refused = _run("PreToolUse", **_bash("gh pr create --fill"))

    assert {e["mode"] for e in compacted.entries} == {"packages"}
    assert refused.refusal and "Open as a draft." in refused.refusal
