import json
import sys

from lemonaid.tasks.checker import corpus, replay

from ..shared import idle, snapshot, task

_EXAMPLE = [sys.executable, "-m", "lemonaid.tasks.checker.default"]


def _corpus(tmp_path, snapshots):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"snapshots": snapshots}))
    return corpus.load(path)


def test_replay_lists_unexpected_and_changed_verdicts(tmp_path):
    snapshots = _corpus(
        tmp_path,
        [
            snapshot(
                [task(), task(task_id="t2", lifecycle="closed")],
                idle(),
                expected={"t1": "challenge", "t2": "wait"},
            )
        ],
    )

    verdicts = list(replay.replay(_EXAMPLE, snapshots, timeout=30))
    replay.write_baseline(tmp_path / "base.tsv", verdicts)

    assert [(v.task_id, v.verdict) for v in verdicts] == [("t1", "challenge"), ("t2", "ok")]
    assert [(v.task_id, why) for v, why in replay.changed(verdicts, {})] == [
        ("t2", "expected wait")
    ]
    assert replay.load_baseline(tmp_path / "base.tsv") == {"s1/t1": "challenge", "s1/t2": "ok"}
    assert [why for _, why in replay.changed(verdicts, {"s1/t1": "wait"})] == [
        "was wait",
        "expected wait",
    ]


def test_checker_failure_is_reported_not_treated_as_a_verdict(tmp_path):
    snapshots = _corpus(tmp_path, [snapshot([task()], idle())])
    checker = tmp_path / "bad.sh"
    checker.write_text("#!/bin/sh\nprintf 'protocol\\t1\\nok\\tother\\tfine\\n'\n")
    checker.chmod(0o755)

    [verdict] = replay.replay([str(checker)], snapshots, timeout=30)

    assert verdict.verdict == "failure"
    assert "other tasks" in verdict.records[0][2]
