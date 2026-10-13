"""The roles a lemon's briefs imply, and the optional Stop hook that requires their waiters."""

import datetime
import json
from pathlib import Path

import pytest

from lemonaid.brief import attached, child, identity, roles
from lemonaid.brief import store as brief_store
from lemonaid.claude import role_waiters
from lemonaid.inbox import db
from lemonaid.lemon_facts import role_waiters as doctor
from lemonaid.lineage import links
from lemonaid.watch import pr_open, registry

_SESSION = "abcd1234-0000-0000-0000-000000000000"
_CHANNEL = "claude:abcd1234"
_PR = "https://github.com/o/r/pull/12"
_PRS = f"""
## Now

### PRs

| Work | PR | Review |
|---|---|---|
| The thing | [r#12]({_PR}) | |
"""


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(pr_open, "_ask", lambda repo, number: "OPEN" if number == 12 else "")


def _brief(name: str, text: str, channel: str = "", parent: str = "") -> str:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\n{text}")
    with db.connect() as conn:
        if channel:
            db.add(conn, channel, "", metadata={"session_id": _SESSION})
            attached.attach(conn, channel, path)
        lemon_id = identity.ensure(conn, path)
        if parent:
            links.set_parent(conn, lemon_id, parent)
        return lemon_id


def _author(tmp_path: Path, doc: bool = True) -> str:
    """An author under a lead, with a sibling reviewer of #12 when *doc*."""
    lead = _brief("lead", "Status: blocked\n")
    author = _brief("author", _PRS, _CHANNEL, lead)
    if doc:
        _brief(
            "reviewer",
            f"Reviews: {_PR}\n\nOutput-Doc: {tmp_path / 'review.md'}\n\n## Goal\n",
            parent=lead,
        )
    return author


def _stop(capsys, **extra) -> dict | None:
    role_waiters.handle(json.dumps({"session_id": _SESSION, **extra}))
    out = capsys.readouterr().out
    return json.loads(out) if out else None


def test_the_reviews_line_names_the_pr_and_a_table_row_is_authored_unless_reviewed():
    text = f"Reviews: {_PR}\n\n{_PRS}"

    assert roles.reviewing(text) == roles.PR("o/r", 12)
    assert roles.authoring(text) == []
    assert roles.authoring(_PRS) == [roles.PR("o/r", 12)]


def test_a_review_brief_records_the_pr_it_reviews():
    today = datetime.date(2026, 10, 12)
    text = child.render(
        "## Goal\n", "Review", "r.AbcDefGh", ("p.Parent", ""), today, {}, "", "", _PR
    )

    assert roles.reviewing(text) == roles.PR("o/r", 12)


def test_an_author_is_asked_for_its_pr_waiter_and_the_reviewers_doc_waiter(tmp_path, capsys):
    _author(tmp_path)

    blocked = _stop(capsys)

    assert blocked is not None
    assert "watch pr --wait 12 --repo o/r" in blocked["reason"]
    assert f"watch doc --wait {tmp_path / 'review.md'}" in blocked["reason"]


def test_an_author_without_a_reviewer_is_asked_for_only_the_pr_waiter(tmp_path, capsys):
    _author(tmp_path, doc=False)

    blocked = _stop(capsys)

    assert blocked is not None
    assert "watch pr" in blocked["reason"]
    assert "watch doc" not in blocked["reason"]


def test_a_running_pr_waiter_leaves_only_the_doc_waiter_missing(tmp_path, capsys):
    _author(tmp_path)

    with registry.registered("pr", ["o/r#12"], _CHANNEL, "pr"):
        blocked = _stop(capsys)

    assert blocked is not None
    assert "watch pr" not in blocked["reason"]
    assert "watch doc" in blocked["reason"]


def test_running_waiters_let_the_turn_end(tmp_path, capsys, monkeypatch):
    _author(tmp_path)
    monkeypatch.setattr(registry, "mine", lambda channel, kind, target: [object()])

    assert _stop(capsys) is None


def test_a_closed_pr_requires_nothing(tmp_path, monkeypatch, capsys):
    _author(tmp_path)
    monkeypatch.setattr(pr_open, "is_open", lambda repo, number: False)

    assert _stop(capsys) is None


def test_a_reviewer_is_asked_for_its_pr_and_its_own_doc(tmp_path, capsys):
    _brief(
        "reviewer",
        f"Reviews: {_PR}\n\nOutput-Doc: {tmp_path / 'review.md'}\n\n## Goal\n",
        _CHANNEL,
    )

    blocked = _stop(capsys)

    assert blocked is not None
    assert "Reviewer (" in blocked["reason"]
    assert "watch pr --wait 12" in blocked["reason"]
    assert "review.md" in blocked["reason"]


def test_a_lead_is_asked_for_each_unfinished_childs_output_doc(tmp_path, capsys):
    lead = _brief("lead", "Status: blocked\n", _CHANNEL)
    _brief("open", f"Output-Doc: {tmp_path / 'open.md'}\n\n## Goal\n", parent=lead)
    _brief("done", f"Status: done\n\nOutput-Doc: {tmp_path / 'done.md'}\n\n## Goal\n", parent=lead)

    blocked = _stop(capsys)

    assert blocked is not None
    assert "open.md" in blocked["reason"]
    assert "done.md" not in blocked["reason"]


def test_a_second_stop_is_let_through(tmp_path, capsys):
    _author(tmp_path)

    assert _stop(capsys, stop_hook_active=True) is None


def test_the_doctor_lists_what_a_lemon_is_missing(tmp_path, capsys):
    author = _author(tmp_path)

    with db.connect() as conn:
        assert doctor.run(conn, [author], as_json=False)

    shown = capsys.readouterr().out
    assert "1 missing role waiters" in shown
    assert "watch pr --wait 12" in shown


def test_the_doctor_is_quiet_when_nothing_is_missing(tmp_path, capsys):
    author = _author(tmp_path, doc=False)

    with registry.registered("pr", ["o/r#12"], _CHANNEL, "pr"), db.connect() as conn:
        assert not doctor.run(conn, [author], as_json=False)

    assert "0 missing" in capsys.readouterr().out


def test_the_pr_state_is_cached_between_calls(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(pr_open, "_ask", lambda repo, number: calls.append(number) or "OPEN")

    assert pr_open.is_open("o/r", 12)
    assert pr_open.is_open("o/r", 12)
    assert calls == [12]


def test_an_unknown_pr_state_counts_as_closed(monkeypatch):
    monkeypatch.setattr(pr_open, "_ask", lambda repo, number: "")

    assert not pr_open.is_open("o/r", 12)


def test_a_merged_pr_is_not_asked_about_again(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(pr_open, "_ask", lambda repo, number: calls.append(number) or "MERGED")
    monkeypatch.setattr(pr_open.time, "time", lambda: 1000.0)
    assert not pr_open.is_open("o/r", 12)
    monkeypatch.setattr(pr_open.time, "time", lambda: 10_000.0)

    assert not pr_open.is_open("o/r", 12)
    assert calls == [12]


def test_header_lines_inside_a_code_fence_or_below_a_section_are_ignored():
    text = f"# t\n\n```\nReviews: {_PR}\n```\n\n## Goal\n\nReviews: {_PR}\n"

    assert roles.reviewing(text) is None
