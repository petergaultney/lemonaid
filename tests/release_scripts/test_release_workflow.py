"""Exercise the release planner's shell without network, tags or publishing."""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("test_status", "current", "published", "expected", "polls"),
    [
        ("in_progress", "tip", "true", "defer", 3),
        ("queued", "tip", "true", "defer", 3),
        ("missing", "tip", "true", "defer", 0),
        ("failure", "tip", "true", "defer", 0),
        ("cancelled", "tip", "true", "defer", 0),
        ("success", "new-tip", "true", "defer", 0),
        ("success", "tip", "true", "tag", 0),
        ("in_progress", "tip", "false", "resume", 0),
        ("queued in_progress success", "tip", "true", "tag", 2),
        ("in_progress failure", "tip", "true", "defer", 1),
        ("waiting pending requested success", "tip", "true", "tag", 3),
        ("in_progress success", "new-tip", "true", "defer", 1),
    ],
)
def test_plan_requires_success_on_current_main(
    tmp_path: Path, test_status: str, current: str, published: str, expected: str, polls: int
):
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text()
    planner = textwrap.dedent(workflow.split("        run: |\n", 1)[1].split("\n  build:")[0])
    stubs = r"""
    gh() {
      case "$1 $2" in
        "release view") echo "$PUBLISHED" ;;
        "run list")
          [[ " $* " == *" --commit tip "* ]] || return 1
          [[ " $* " != *" --status success "* ]] || return 1
          statuses=($TEST_STATUS)
          index=$(cat "$STATUS_INDEX")
          echo "${statuses[index]:-${statuses[${#statuses[@]}-1]}}"
          echo "$((index + 1))" > "$STATUS_INDEX" ;;
        *) return 1 ;;
      esac
    }
    uv() {
      case "$*" in
        *"latest --below"*) echo 0.115.2 ;;
        *latest) echo 0.115.3 ;;
        *"version --since v0.115.3 --until tip") echo 0.115.4 ;;
        *) return 1 ;;
      esac
    }
    git() {
      case "$1" in
        fetch) return 0 ;;
        rev-parse) echo tip ;;
        diff) return 0 ;;
        ls-remote) printf '%s\trefs/heads/main\n' "$CURRENT" ;;
        push) echo "$*" > "$PUSH_LOG" ;;
        *) return 1 ;;
      esac
    }
    sleep() {
      echo "$1" >> "$SLEEP_LOG"
      SECONDS=$((SECONDS + 300))
    }
    """
    output, summary, pushed = (tmp_path / name for name in ("output", "summary", "pushed"))
    status_index, sleeps = tmp_path / "status-index", tmp_path / "sleeps"
    status_index.write_text("0\n")
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", textwrap.dedent(stubs) + planner],
        env={
            **os.environ,
            "TEST_STATUS": test_status,
            "CURRENT": current,
            "PUBLISHED": published,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_REPOSITORY": "example/repo",
            "PUSH_LOG": str(pushed),
            "STATUS_INDEX": str(status_index),
            "SLEEP_LOG": str(sleeps),
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert (sleeps.read_text().splitlines() if sleeps.exists() else []) == ["30"] * polls
    if test_status in ("in_progress", "queued") and published == "true":
        assert "timed out after 15 minutes" in summary.read_text()
    if expected == "defer":
        assert output.read_text() == "release=false\n"
        assert "Release deferred:" in summary.read_text()
        assert not pushed.exists()
    elif expected == "tag":
        assert "version=0.115.4\n" in output.read_text()
        assert pushed.read_text() == "push origin tip:refs/tags/v0.115.4\n"
        assert "Releasing main commit tip" in summary.read_text()
    else:
        assert "version=0.115.3\n" in output.read_text()
        assert "previous=0.115.2\n" in output.read_text()
        assert "Finishing existing tag" in summary.read_text()
        assert not pushed.exists()
