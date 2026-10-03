"""`lemonaid claude resume`, the default Claude resume command, starting on a prompt."""

import argparse

import pytest

from lemonaid.claude import cli, resume


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
