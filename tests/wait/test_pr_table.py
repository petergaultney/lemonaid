import argparse
import dataclasses

import pytest

from lemonaid.brief import command, verbs_cli
from lemonaid.watch import pr_activity, pr_comments, subscriptions

from . import shared


@pytest.mark.parametrize("event", ["ci-failed", "comment"])
def test_pr_table_stays_subscribed_after_a_progress_update(tmp_path, monkeypatch, event):
    path = tmp_path / "brief.md"
    path.write_text(shared.BRIEF)
    monkeypatch.setattr(command, "own_brief", lambda args: (path, ""))
    parser = argparse.ArgumentParser()
    verbs_cli.add_parsers(parser.add_subparsers())

    def run(*words):
        args = parser.parse_args([*words, "--self"])
        args.func(args)

    run("pr", "add", "https://github.com/o/r/pull/12", "Fix")
    snapshot = pr_activity.Snapshot(
        "b" * 40,
        "OPEN",
        False,
        "",
        [],
        "main",
        "MERGEABLE",
        [pr_activity.Check("test", False, "pending")],
    )
    current = [snapshot]
    monkeypatch.setattr(pr_activity, "fetch", lambda *args, **kwargs: current[0])
    report = subscriptions.report

    def fast_report(*args, **kwargs):
        reading = report(*args, **kwargs)
        return dataclasses.replace(
            reading, specs=tuple(dataclasses.replace(s, interval=0.01) for s in reading.specs)
        )

    monkeypatch.setattr(subscriptions, "report", fast_report)
    sent = []
    path, _inbox, root, stop, thread, errors = shared.start(tmp_path, path.read_text(), sent.append)
    try:
        shared.eventually(lambda: bool(list((root / "pr").glob("*.merge.json"))))
        run("now", "- Reviewer cleared the PR. CI running.")
        assert "\n## PRs\n" in path.read_text()
        assert not path.read_text().split("## Watching", 1)[1].strip()
        if event == "ci-failed":
            current[0] = snapshot._replace(checks=[pr_activity.Check("test", False, "failed")])
        else:
            current[0] = snapshot._replace(
                comments=[pr_comments.Comment("new", "conversation", "sam", "Please fix", "OWNER")]
            )
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1
        assert ("CI failed" if event == "ci-failed" else "Please fix") in sent[0]
    finally:
        stop.set()
        thread.join(5)
