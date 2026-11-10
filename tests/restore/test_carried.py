"""The launch flags a resumed lemon keeps."""

import pytest

from lemonaid.restore import carried


def test_a_claude_keeps_its_model_and_effort_and_nothing_else():
    argv = ["claude", "--model", "haiku", "--allow-dangerously-skip-permissions", "--effort=low"]

    assert carried.flags("claude", [*argv, "--session-id", "x"]) == [
        "--model",
        "haiku",
        "--effort",
        "low",
    ]


def test_a_codex_keeps_its_model_and_reasoning_effort_overrides_only():
    argv = ["codex", "-m", "gpt-5", "-c", "model_reasoning_effort=high", "-c", "other=1"]

    assert carried.flags("codex", argv) == ["-m", "gpt-5", "-c", "model_reasoning_effort=high"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            ["lemonaid", "claude", "resume", "ID"],
            ["lemonaid", "claude", "--model", "haiku", "--resume", "ID"],
            id="lemonaid-resume-becomes-flags",
        ),
        pytest.param(
            ["lemonaid", "claude", "--model", "opus", "--resume", "ID"],
            ["lemonaid", "claude", "--model", "opus", "--resume", "ID"],
            id="configured-model-wins",
        ),
        pytest.param(
            ["opencode", "--session", "ID"], ["opencode", "--session", "ID"], id="no-claude-there"
        ),
    ],
)
def test_a_claude_resume_line_gains_the_flags_it_lacks(line, expected):
    assert carried.apply("claude", line, ["--model", "haiku"]) == expected


def test_a_codex_resume_line_gains_its_model_before_the_subcommand():
    assert carried.apply("codex", ["codex", "--model", "o3", "resume", "T"], ["-m", "gpt-5"]) == [
        "codex",
        "--model",
        "o3",
        "resume",
        "T",
    ]
    assert carried.apply("codex", ["codex", "resume", "T"], ["-m", "gpt-5"]) == [
        "codex",
        "-m",
        "gpt-5",
        "resume",
        "T",
    ]
