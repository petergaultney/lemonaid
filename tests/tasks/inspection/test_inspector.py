import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from lemonaid.inbox import db
from lemonaid.lemon_facts import facts
from lemonaid.messages import store
from lemonaid.tasks.checker import corpus, protocol, replay, session
from lemonaid.tasks.checker.default import rules
from lemonaid.tasks.inspection import cases, challenges, inspect_cli, inspector, memory, passes
from lemonaid.tasks.model import associations, dependencies, holding, ledger, lifecycle
from lemonaid.watch import pr_activity

from ..shared import new_task

_NOW = 1_800_000_000.0
_LONG_AGO = _NOW - 3600


def _seen(lemon_id: str, state: str = "listening", **changes) -> facts.Facts:
    return dataclasses.replace(
        facts.Facts(
            lemon_id=lemon_id,
            channel=f"claude:{lemon_id}",
            brief=f"/{lemon_id}.md",
            status="",
            parent="",
            archived=False,
            snoozed=False,
            state=state,
            state_detail="",
            harness_running=True,
            inbox_waiter=True,
            pane=None,
            waiters_listed=[],
            waiters_running=[],
            messages_queued=0,
            exited_at=None,
            exit_reason="",
            last_activity=_LONG_AGO,
            recent_starts=0,
        ),
        **changes,
    )


def _observers(*seen: facts.Facts) -> inspector.Observers:
    return inspector.Observers(lambda _conn: {f.lemon_id: f for f in seen}, lambda _key: None)


def _ask(argv: tuple[str, ...]) -> session.Ask:
    """The default checker in-process, or a file-mode checker run once per request."""
    if not argv:
        return rules.respond

    return lambda operation, text: replay.run_checker(argv, text, 30, operation)


def _run(conn, *seen: facts.Facts, argv=(), remembered=None, **kw) -> inspector.Pass:
    return inspector.run(conn, _NOW, _ask(argv), {}, _observers(*seen, **kw), remembered)


def _brief(conn, brief_id: str, text: str = "# Work\n") -> Path:
    path = Path(os.environ["LEMONAID_BRIEFS_DIR"]) / f"{brief_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    conn.execute(
        "INSERT OR REPLACE INTO lemon_identities (lemon_id, path) VALUES (?, ?)",
        (brief_id, str(path)),
    )
    conn.commit()
    return path


def _started(conn, brief_id: str = "Work.alpha") -> str:
    """A task whose holder started long ago; its brief declares no wait."""
    _brief(conn, brief_id)
    task = new_task(conn, brief_id=brief_id, request_id=f"t-{brief_id}")
    with ledger.transaction(conn):
        holding.attach(conn, brief_id, brief_id, 100.0)
    return task


def _open(conn) -> list[tuple[str, str, str]]:
    return [(c["subject"], c["obligation"], c["target"]) for c in cases.open_cases(conn)]


def test_an_idle_holder_is_challenged_once_and_the_case_resolves_once_it_has_worked():
    with db.connect() as conn:
        task = _started(conn)

        first = _run(conn, _seen("Work.alpha"))
        again = _run(conn, _seen("Work.alpha"))
        assert _open(conn) == [(f"task:{task}", "progress", "Work.alpha")]
        _run(conn, _seen("Work.alpha", state="mid-turn"))
        while_busy = _open(conn)
        _run(conn, _seen("Work.alpha", last_activity=_NOW - 10))

        assert (first.evaluated, len(first.opened), len(again.opened)) == (1, 1, 0)
        assert len(while_busy) == 1 and _open(conn) == []


def test_a_checker_failure_keeps_the_open_cases():
    with db.connect() as conn:
        task = _started(conn)
        _run(conn, _seen("Work.alpha"))

        broken = _run(conn, _seen("Work.alpha"), argv=("false",))

        assert broken.failures and broken.failures[0][0] == f"task:{task}"
        assert cases.finding(conn, task) == "failure"
        assert _open(conn) == [(f"task:{task}", "progress", "Work.alpha")]


def test_a_gone_holders_task_goes_back_to_whoever_handed_it_over():
    with db.connect() as conn:
        task = _started(conn, "Lead.lead")
        with ledger.transaction(conn):
            holding.assign(conn, task, 2, "brief:Gone.one", "", True, "Lead.lead", "g", 102.0)

        _run(conn, _seen("Gone.one", state="dead"), _seen("Lead.lead"))

        assert (f"task:{task}", "holder-unavailable", "Lead.lead") in _open(conn)


def test_a_waiting_parent_is_judged_by_its_childs_last_finding():
    with db.connect() as conn:
        parent, child = _started(conn, "Lead.lead"), _started(conn, "Child.one")
        with ledger.transaction(conn):
            dependencies.depend(conn, parent, 2, child, "Lead.lead", "dep", 103.0)

        recent = _seen("Child.one", last_activity=_NOW - 10)
        _run(conn, _seen("Lead.lead"), recent)
        _run(conn, _seen("Lead.lead"), recent)

        assert cases.finding(conn, parent) == "wait"
        assert _open(conn) == []


def test_coverage_challenges_an_idle_working_brief_with_no_task():
    with db.connect() as conn:
        with ledger.transaction(conn):
            associations.exempt(conn, "Lead.lead", "coordinates", "", 1.0)
        for brief in ("Loose.one", "Lead.lead", "Busy.one"):
            _brief(conn, brief)
        _brief(conn, "Done.one", "---\ntype: Brief\nstatus: done\n---\n# Work\n")

        _run(
            conn,
            _seen("Loose.one"),
            _seen("Lead.lead"),
            _seen("Done.one", status="done"),
            _seen("Busy.one", state="mid-turn"),
        )

        assert _open(conn) == [("brief:Loose.one", "missing-task", "Loose.one")]


def test_only_a_brief_status_that_puts_the_move_elsewhere_avoids_a_challenge():
    with db.connect() as conn:
        for brief in ("Blocked.one", "Review.one", "Waiting.one", "Silent.one"):
            _started(conn, brief)
        _brief(
            conn,
            "Blocked.one",
            "---\ntype: Brief\nstatus: blocked\n---\n# Work\n\n## Now\n\n"
            "### Needs Sam\n\n- Accept the design\n",
        )
        _brief(
            conn,
            "Review.one",
            "---\ntype: Brief\nstatus: review\n---\n# Work\n\n## Now\n\n"
            "### Waiting on\n\n- The reviewer\n",
        )
        _brief(conn, "Waiting.one", "# Work\n\n## Now\n\n### Waiting on\n\n- CI on the PR\n")
        _run(conn, *(_seen(b) for b in ("Blocked.one", "Review.one", "Waiting.one", "Silent.one")))

        assert [target for _, _, target in _open(conn)] == ["Waiting.one", "Silent.one"]


def test_a_status_covers_every_task_its_brief_holds():
    with db.connect() as conn:
        one = _started(conn)
        other = new_task(conn, request_id="other")
        with ledger.transaction(conn):
            holding.attach(conn, "Work.alpha", "Work.alpha", 100.0)
        _brief(conn, "Work.alpha", "---\ntype: Brief\nstatus: merge\n---\n# Work\n")
        _run(conn, _seen("Work.alpha"))

        assert (cases.finding(conn, one), cases.finding(conn, other)) == ("wait", "wait")


def test_a_brief_with_no_task_asks_its_nearest_ancestor_that_has_one():
    with db.connect() as conn:
        for brief in ("Child.one", "Grandchild.one", "Loose.one"):
            _brief(conn, brief)
        conn.executemany(
            "INSERT INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES (?, ?, 0)",
            [("Child.one", "Lead.lead"), ("Grandchild.one", "Child.one")],
        )
        conn.commit()
        with ledger.transaction(conn):
            associations.exempt(conn, "Lead.lead", "coordinates", "", 1.0)
        _run(conn, _seen("Child.one"), _seen("Grandchild.one"), _seen("Loose.one"))
        reasons = {c["target"]: c["reason"] for c in cases.open_cases(conn)}

    assert "`lemonaid tell Lead.lead`" in reasons["Child.one"]
    assert "`lemonaid tell Lead.lead`" in reasons["Grandchild.one"]  # Child.one has no task
    assert "tell" not in reasons["Loose.one"]


def test_an_unanswered_challenge_is_sent_again_with_doubling_gaps_up_to_the_ceiling():
    with db.connect() as conn:
        _started(conn)
        _run(conn, _seen("Work.alpha"))

        def sent(at: float) -> int:
            return len(challenges.deliver(conn, 100, 300, (), _NOW + at))

        timeline = [sent(at) for at in (0, 99, 100, 299, 300, 599, 600, 899, 900)]

    assert timeline == [1, 0, 1, 0, 1, 0, 1, 0, 1]
    assert len(list(store.inbox_for_id("Work.alpha").glob("*.md"))) == 5


def test_a_challenge_reopened_after_an_unrelated_turn_keeps_its_backoff():
    with db.connect() as conn:
        _started(conn)
        _run(conn, _seen("Work.alpha"))
        (case,) = cases.open_cases(conn)
        record = ("challenge", case["subject"], case["obligation"], case["evidence"], "brief")
        record += (case["target"], case["reason"])

        def reopened(at: float) -> None:
            with ledger.transaction(conn):
                cases.apply(conn, case["subject"], 1, [], _NOW + at - 1, case["basis"])
                cases.apply(conn, case["subject"], 1, [record], _NOW + at, case["basis"])

        def sent(at: float) -> int:
            return len(challenges.deliver(conn, 100, 300, (), _NOW + at))

        timeline = [sent(0), sent(100)]
        reopened(150)
        timeline += [sent(150), sent(299), sent(300)]
        record = (*record[:5], "Other.one", record[6])
        reopened(350)
        timeline.append(sent(350))

    assert timeline == [1, 1, 0, 0, 1, 1]  # a new recipient starts its own backoff


def test_a_custom_checker_writes_the_words_a_brief_with_no_task_reads(tmp_path):
    script = tmp_path / "checker.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "from lemonaid.tasks.checker import checker_input, protocol\n"
        "view = checker_input.read(Path(sys.argv[3]).read_text())\n"
        "if sys.argv[1] == 'describe':\n"
        "    sys.stdout.write(protocol.render([]))\n"
        "elif view.kind == 'brief':\n"
        "    record = ('challenge', view.subject, 'missing-task', '', 'brief', view.subject,"
        " 'our own words')\n"
        "    sys.stdout.write(protocol.render([record]))\n"
        "else:\n"
        "    sys.stdout.write(protocol.render([('ok', view.subject, 'fine')]))\n"
    )
    with db.connect() as conn:
        _brief(conn, "Loose.one")
        _run(conn, _seen("Loose.one"), argv=(sys.executable, str(script)))
        sent = challenges.deliver(conn, 300, 86400, (), _NOW)

    [message] = store.inbox_for_id("Loose.one").glob("*.md")
    assert len(sent) == 1 and "our own words" in message.read_text()


def test_challenges_go_to_every_brief_not_opted_out_and_only_once():
    with db.connect() as conn:
        for brief in ("Work.alpha", "Work.bravo", "Quiet.one"):
            _started(conn, brief)
        _run(conn, _seen("Work.alpha"), _seen("Work.bravo"), _seen("Quiet.one"))

        first = challenges.deliver(conn, 300, 86400, {"Quiet.one"}, _NOW)
        again = challenges.deliver(conn, 300, 86400, {"Quiet.one"}, _NOW)

    assert len(first) == 2 and again == []
    assert len(list(store.inbox_for_id("Work.alpha").glob("*.md"))) == 1
    assert len(list(store.inbox_for_id("Work.bravo").glob("*.md"))) == 1
    assert not store.inbox_for_id("Quiet.one").exists()


def test_a_dry_run_sends_nothing_and_leaves_the_challenge_for_a_later_pass():
    with db.connect() as conn:
        _started(conn, "Work.alpha")
        _run(conn, _seen("Work.alpha"))

        dry = challenges.deliver(conn, 0, 86400, (), _NOW)
        sent = challenges.deliver(conn, 300, 86400, (), _NOW)

    assert len(dry) == 1 and dry[0].startswith("would tell Work.alpha")
    assert len(sent) == 1 and sent[0].startswith("told Work.alpha")
    assert len(list(store.inbox_for_id("Work.alpha").glob("*.md"))) == 1


def test_closing_or_reassigning_a_task_resolves_its_old_challenges():
    with db.connect() as conn:
        closed, moved = _started(conn, "Work.alpha"), _started(conn, "Work.bravo")
        _run(conn, _seen("Work.alpha"), _seen("Work.bravo"))
        with ledger.transaction(conn):
            lifecycle.close(conn, closed, 2, "finished", "Work.alpha", "close", _NOW)
            holding.assign(
                conn,
                moved,
                2,
                "brief:Review.one",
                "",
                True,
                "Work.bravo",
                "mv",
                _NOW,
            )

        sent = challenges.deliver(conn, 300, 86400, (), _NOW)
        _run(conn, _seen("Work.alpha"), _seen("Work.bravo"), _seen("Review.one"))

        assert sent == [] and _open(conn) == []


def test_a_task_closed_on_an_open_pr_is_challenged_once_until_the_pr_merges(dead):
    url = "https://github.com/acme/widgets/pull/7"
    states = ["", "OPEN", "OPEN", "MERGED", "MERGED"]  # "" while no snapshot is seen

    def pr(_key):
        if not states[0]:
            return None

        return pr_activity.Snapshot("abc", states[0], False, "", [], "main", "MERGEABLE", [])

    with db.connect() as conn:
        made = _started(conn)
        with ledger.transaction(conn):
            lifecycle.set_url(conn, made, 2, url, "its PR", "Work.alpha", "url", _NOW - 5)
            lifecycle.close(conn, made, 3, "finished", "Work.alpha", "close", _NOW - 4)
        observers = inspector.Observers(lambda _conn: {"Work.alpha": _seen("Work.alpha")}, pr)
        judged, found = [], []
        while states:
            judged.append(inspector.run(conn, _NOW, rules.respond, {}, observers).evaluated)
            found.append(_open(conn))
            states.pop(0)

    assert judged == [1, 1, 1, 1, 0]
    assert found[0] == [] and found[3:] == [[], []]
    assert found[1:3] == [[(f"task:{made}", "closed-unmerged", "Work.alpha")]] * 2


def test_reopening_or_closing_a_task_again_drops_the_challenge_about_its_closing(dead):
    url = "https://github.com/acme/widgets/pull/7"

    def pr(_key):
        return pr_activity.Snapshot("abc", "OPEN", False, "", [], "main", "MERGEABLE", [])

    with db.connect() as conn:
        made = _started(conn)
        with ledger.transaction(conn):
            lifecycle.set_url(conn, made, 2, url, "its PR", "Work.alpha", "url", _NOW - 5)
            lifecycle.close(conn, made, 3, "finished", "Work.alpha", "close", _NOW - 4)
        observers = inspector.Observers(lambda _conn: {"Work.alpha": _seen("Work.alpha")}, pr)
        inspector.run(conn, _NOW, rules.respond, {}, observers)
        opened = _open(conn)
        with ledger.transaction(conn):
            lifecycle.reopen(conn, made, 4, "not finished", "Work.alpha", "reopen", _NOW + 1)
            lifecycle.close(conn, made, 5, "accepted", "cli", "accepted", _NOW + 2)

        sent = challenges.deliver(conn, 300, 86400, (), _NOW + 3)
        left = _open(conn)

    assert opened == [(f"task:{made}", "closed-unmerged", "Work.alpha")]
    assert sent == [] and left == []


def test_a_closed_task_is_told_about_once_and_not_while_an_unclosed_task_has_its_pr(dead):
    url = "https://github.com/acme/widgets/pull/7"

    def pr(_key):
        return pr_activity.Snapshot("abc", "OPEN", False, "", [], "main", "MERGEABLE", [])

    observers = inspector.Observers(lambda _conn: {"Work.alpha": _seen("Work.alpha")}, pr)
    with db.connect() as conn:
        _brief(conn, "Work.alpha")
        alone, review, _work = (
            new_task(conn, request_id=name, subject_url_text=pr_url)
            for name, pr_url in (("alone", url + "0"), ("review", url), ("work", url))
        )
        with ledger.transaction(conn):
            holding.attach(conn, "Work.alpha", "Work.alpha", 100.0)
            for made in (alone, review):
                lifecycle.close(conn, made, 2, "finished", "Work.alpha", "close", _NOW - 4)
            holding.assign(  # a parent's final check still carries the PR
                conn,
                _work,
                2,
                "brief:Work.alpha",
                "",
                True,
                "Work.alpha",
                "check",
                _NOW - 4,
                check=True,
            )
        inspector.run(conn, _NOW, rules.respond, {}, observers)
        sent = [challenges.deliver(conn, 300, 86400, (), _NOW + d) for d in (0, 3600, 86400)]
        found = [c for c in _open(conn) if c[1] == "closed-unmerged"]

    assert found == [(f"task:{alone}", "closed-unmerged", "Work.alpha")]
    assert [sum("closed-unmerged" in line for line in s) for s in sent] == [1, 0, 0]


def test_a_parent_gets_the_idle_grace_from_when_its_child_closed():
    with db.connect() as conn:
        parent, child = _started(conn, "Lead.lead"), _started(conn, "Child.one")
        with ledger.transaction(conn):
            dependencies.depend(conn, parent, 2, child, "Lead.lead", "dep", 103.0)
            lifecycle.close(conn, child, 2, "finished", "Child.one", "close", _NOW - 10)

        _run(conn, _seen("Lead.lead"), _seen("Child.one"))

        assert cases.finding(conn, parent) == "ok" and _open(conn) == []


def test_a_mid_turn_holder_or_brief_is_not_inspected():
    with db.connect() as conn:
        task = _started(conn)
        _brief(conn, "Loose.one")

        found = _run(
            conn, _seen("Work.alpha", state="mid-turn"), _seen("Loose.one", state="mid-turn")
        )

        assert found.evaluated == 0 and cases.finding(conn, task) == "" and _open(conn) == []


def test_an_evaluation_older_than_the_latest_is_dropped(monkeypatch):
    with db.connect() as conn:
        task = _started(conn)

        def newer_pass_finishes_first(_operation, _text):
            with ledger.transaction(conn):
                cases.apply(conn, f"task:{task}", 2, [("ok", task, "working")], _NOW + 1, "")
            stale = ("challenge", task, "progress", "2", "brief", "Work.alpha", "idle")
            return protocol.render([stale])

        old = corpus.Input("old", task, "")
        inspector._evaluate(
            conn,
            ledger.state(conn, task),
            lambda: old,
            newer_pass_finishes_first,
            memory.new(),
            _NOW,
        )

        assert _open(conn) == [] and cases.finding(conn, task) == "ok"


_CUSTOM_CHECKER = """
import sys
from pathlib import Path

from lemonaid.tasks.checker import checker_input, protocol

operation, _, path = sys.argv[1:4]
view = checker_input.read(Path(path).read_text())
watched = Path(sys.argv[0]).with_name("watched.md")
if operation == "describe":
    sys.stdout.write(protocol.render([("watch", "brief", "Work.alpha"), ("watch", "file", str(watched))]))
    raise SystemExit

status = view.facts[("brief", "Work.alpha", "status")]
digest = view.facts[("file", str(watched), "sha256")].value
captured = Path(view.facts[("file", str(watched), "captured")].value).read_text()
assert (status.availability, status.value, captured) == ("known", "", "draft")
found = (
    ("ok", view.subject, "seen before")
    if any(c["obligation"] == "read-doc" for c in view.cases.values())
    else ("challenge", view.subject, "read-doc", digest, "brief", "Work.alpha", "read it")
)
sys.stdout.write(protocol.render([found]))
"""


def test_a_custom_checker_gets_the_watches_it_declares_and_its_open_cases(tmp_path):
    script = tmp_path / "checker.py"
    script.write_text(_CUSTOM_CHECKER)
    (tmp_path / "watched.md").write_text("draft")
    argv = (sys.executable, str(script))
    with db.connect() as conn:
        task = _started(conn)

        first = _run(conn, _seen("Work.alpha"), argv=argv)
        assert first.failures == [] and _open(conn) == [(f"task:{task}", "read-doc", "Work.alpha")]
        second = _run(conn, _seen("Work.alpha"), argv=argv)

        assert second.failures == [] and _open(conn) == []


def test_a_checker_watching_something_lemonaid_cant_observe_is_a_failure(tmp_path):
    script = tmp_path / "checker.py"
    script.write_text("import sys\nprint('protocol\\t1')\nprint('watch\\tslack\\t#general')\n")
    with db.connect() as conn:
        task = _started(conn)

        found = _run(conn, _seen("Work.alpha"), argv=(sys.executable, str(script)))

    assert found.failures == [
        (f"task:{task}", "the checker watches slack, which lemonaid can't observe")
    ]


def test_a_second_concurrent_pass_is_skipped(capsys):
    args = argparse.Namespace(json=True, dry_run=True)
    with passes.sole() as mine:
        inspect_cli._cmd_inspect(args)

    assert mine and json.loads(capsys.readouterr().out)["skipped"] is True


def test_a_remembered_pass_asks_the_checker_again_only_about_what_changed():
    asked = []

    def counting(operation: str, text: str) -> str:
        asked.append(operation)
        return rules.respond(operation, text)

    remembered = memory.new()
    with db.connect() as conn:
        _started(conn)

        def run(*seen: facts.Facts) -> None:
            asked.clear()
            inspector.run(conn, _NOW, counting, {}, _observers(*seen), remembered)

        run(_seen("Work.alpha"))
        first = list(asked)
        run(_seen("Work.alpha"))  # the challenge it opened is new input
        run(_seen("Work.alpha"))
        unchanged = list(asked)
        run(_seen("Work.alpha", last_activity=_LONG_AGO + 60))

    assert first == ["describe", "evaluate"] and unchanged == [] and asked == ["evaluate"]


def test_a_bad_time_from_the_checker_fails_that_subject_and_the_pass_goes_on():
    with db.connect() as conn:
        bad, good = _started(conn, "Work.alpha"), _started(conn, "Work.bravo")

        def checker(operation: str, text: str) -> str:
            if operation == "evaluate" and bad in text:
                return protocol.render([("ok", bad, "x"), ("recheck", bad, "not-a-time")])

            return rules.respond(operation, text)

        found = inspector.run(
            conn, _NOW, checker, {}, _observers(_seen("Work.alpha"), _seen("Work.bravo"))
        )

        judged = cases.finding(conn, good)

    assert [s for s, _ in found.failures] == [f"task:{bad}"]
    assert found.evaluated == 2 and judged != ""
