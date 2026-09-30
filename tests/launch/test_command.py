"""The harness line: Codex gets past its startup prompts, and the prompt is one word."""

from pathlib import Path

from lemonaid.launch import command


def test_codex_trusts_its_directory_and_skips_the_update_check():
    line = command.harness_line("/opt/bin/codex --no-daemon", Path("/work/it's here"), "go")

    assert line.startswith("/opt/bin/codex -c ")
    assert """'projects={"/work/it'"'"'s here"={trust_level="trusted"}}'""" in line
    assert line.endswith("-c check_for_update_on_startup=false --no-daemon go")


def test_other_harnesses_are_left_alone():
    line = "lemonaid claude patch && claude --remote-control"

    assert command.harness_line(line, Path("/w"), "read it; go") == f"{line} 'read it; go'"


def test_a_line_with_no_prompt_gets_none():
    assert command.harness_line("codex", Path("/w")).endswith("check_for_update_on_startup=false")


def test_only_a_codex_on_the_shared_daemon_is_unclaimable():
    assert "--no-daemon" in command.unclaimable("codex -m gpt")
    assert command.unclaimable("codex --no-daemon") == ""
    assert command.unclaimable("claude --remote-control") == ""
