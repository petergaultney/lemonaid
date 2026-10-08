"""`lemonaid claude resume`, the default Claude resume command, starting on a prompt."""

import argparse
import json

import pytest

from lemonaid.claude import cli, projects, resume


@pytest.fixture
def execs(monkeypatch, tmp_path) -> list[list[str]]:
    started: list[list[str]] = []
    monkeypatch.setattr(resume, "find_session_project", lambda _: str(tmp_path))
    monkeypatch.setattr(resume.os, "chdir", lambda _: None)
    monkeypatch.setattr(resume.os, "execvp", lambda _, argv: started.append(argv))
    return started


def _run(*argv: str) -> None:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["claude", "resume", *argv])
    args.func(args)


def test_a_prompt_after_the_session_id_starts_the_resumed_session(execs):
    _run("abc123", "rearm your waiters")

    assert execs == [["claude", "--resume", "abc123", "rearm your waiters"]]


def test_without_a_prompt_it_resumes_as_before(execs):
    _run("abc123")

    assert execs == [["claude", "--resume", "abc123"]]


def test_missing_directory_resumes_transcript_in_surviving_parent(monkeypatch, tmp_path):
    removed = tmp_path / "gone"
    config = tmp_path / "claude"
    transcript = config / "projects" / "encoded-old-directory" / "session-id.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setattr(resume, "find_session_project", lambda _: str(removed))
    directories = []
    started = []
    monkeypatch.setattr(resume.os, "chdir", directories.append)
    monkeypatch.setattr(resume.os, "execvp", lambda _, argv: started.append(argv))

    _run("session-id", "rearm your waiters")

    assert directories == [str(tmp_path)]
    assert started == [["claude", "--resume", str(transcript), "rearm your waiters"]]
    assert not removed.exists()


def test_forwarding_preserves_flags_when_directory_is_gone(monkeypatch, tmp_path):
    removed = tmp_path / "gone"
    config = tmp_path / "claude"
    transcript = config / "projects" / "old" / "id.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setattr(resume, "find_session_project", lambda _: str(removed))
    monkeypatch.setattr(resume.os, "chdir", lambda _: None)
    started = []
    monkeypatch.setattr(resume.os, "execvp", lambda _, argv: started.append(argv))

    resume.forward_to_claude(["--allow-dangerously-skip-permissions", "--resume", "id"])

    assert started == [
        ["claude", "--allow-dangerously-skip-permissions", "--resume", str(transcript)]
    ]


@pytest.mark.parametrize("copies", [0, 2])
def test_missing_or_ambiguous_transcript_is_reported(monkeypatch, tmp_path, copies, capsys):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(resume, "find_session_project", lambda _: str(tmp_path / "gone"))
    for index in range(copies):
        transcript = tmp_path / "claude" / "projects" / str(index) / "id.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}\n")

    with pytest.raises(SystemExit):
        _run("id")

    assert "expected one saved transcript" in capsys.readouterr().err


def test_missing_directory_lookup_uses_isolated_claude_state(monkeypatch, tmp_path):
    config = tmp_path / "claude"
    config.mkdir()
    removed = tmp_path / "gone"
    (config / "history.jsonl").write_text(
        json.dumps({"sessionId": "isolated-id", "project": str(removed)}) + "\n"
    )
    transcript = config / "projects" / "old" / "isolated-id.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setattr(resume, "find_session_project", projects.find_session_project)
    started = []
    monkeypatch.setattr(resume.os, "chdir", lambda _: None)
    monkeypatch.setattr(resume.os, "execvp", lambda _, argv: started.append(argv))

    _run("isolated-id")

    assert started == [["claude", "--resume", str(transcript)]]
