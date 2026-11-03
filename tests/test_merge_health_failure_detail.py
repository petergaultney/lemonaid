"""A CI failure names each failed check's page and the errors it annotated."""

from lemonaid.watch import merge_health, pr_activity

_JOB = "https://github.com/acme/widgets/actions/runs/11/job/22"


def _node(**changes) -> dict:
    return {
        "__typename": "CheckRun",
        "name": "pytest (3.12)",
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "completedAt": "2026-11-02T12:00:00Z",
        "detailsUrl": _JOB,
        "isRequired": False,
        "annotations": {"nodes": []},
        **changes,
    }


def _annotation(message: str, level: str = "FAILURE", line: int | None = 4) -> dict:
    return {
        "path": "tests/test_x.py" if line else ".github",
        "message": message,
        "annotationLevel": level,
        "location": {"start": {"line": line}},
    }


def _notice(node: dict) -> str:
    snap = pr_activity.Snapshot(
        "a" * 40, "OPEN", False, "", [], "main", "MERGEABLE", [pr_activity._check(node)]
    )
    events, _ = merge_health.events(90, snap, merge_health.Seen("", ""))
    return events[0].text


def test_a_failed_check_lists_its_page_and_failure_annotations():
    annotations = [
        _annotation("test_x\nassert 1 == 2"),
        _annotation("deprecated", level="WARNING"),
        _annotation("Process completed with exit code 1.", line=None),
    ]

    notice = _notice(_node(annotations={"nodes": annotations}))

    assert notice.endswith(
        f"Failed:\n- pytest (3.12) ({_JOB})\n  - tests/test_x.py:4: test_x assert 1 == 2"
    )


def test_a_failed_check_without_annotations_gives_the_command_for_its_log():
    notice = _notice(
        _node(
            annotations={"nodes": [_annotation("Process completed with exit code 1.", line=None)]}
        )
    )

    assert notice.endswith(
        f"- pytest (3.12) ({_JOB})\n  - its log: `gh run view --job 22 --log-failed`"
    )


def test_a_status_context_gives_its_target_page():
    node = {
        "__typename": "StatusContext",
        "context": "deploy",
        "state": "FAILURE",
        "createdAt": "",
        "targetUrl": "https://ci.example.com/7",
        "isRequired": False,
    }

    assert _notice(node).endswith("Failed:\n- deploy (https://ci.example.com/7)")
