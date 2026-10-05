"""The harness line: Codex gets past its startup prompts, and the prompt is one word."""

import shlex
from pathlib import Path

from lemonaid.launch import command


def test_codex_trusts_its_directory_and_skips_the_update_check():
    line, _ = command.harness_line("/opt/bin/codex --no-daemon", Path("/work/it's here"), "go")

    assert line.startswith("env -u LEMONAID_PROMPT /opt/bin/codex -c ")
    assert """'projects={"/work/it'"'"'s here"={trust_level="trusted"}}'""" in line
    assert line.endswith('-c check_for_update_on_startup=false --no-daemon "$LEMONAID_PROMPT"')


def test_codex_trust_path_keeps_unicode_without_surrogates():
    directory = Path("/work/openclaw-\U0001f99e")

    line, _ = command.harness_line("codex --no-daemon", directory, "go")

    words = shlex.split(line)
    assert words[words.index("-c") + 1] == (f'projects={{"{directory}"={{trust_level="trusted"}}}}')
    assert "\\ud" not in line
    line.encode("utf-8")


def test_other_harnesses_are_left_alone():
    line = "lemonaid claude patch && claude --remote-control"

    assert command.harness_line(line, Path("/w"), "read it; go") == (
        f'{line} "$LEMONAID_PROMPT"',
        {"LEMONAID_PROMPT": "read it; go"},
    )


def test_the_prompt_is_never_spelled_out_in_the_line():
    """The line is typed into a shell whose quoting rules may not be POSIX's (xonsh's aren't)."""
    prompt = """Peter's "brief"; $HOME `x` \\ go"""

    line, environment = command.harness_line("claude", Path("/w"), prompt)

    assert line == 'env -u LEMONAID_PROMPT claude "$LEMONAID_PROMPT"'
    assert environment == {"LEMONAID_PROMPT": prompt}


def test_a_line_with_no_prompt_gets_none():
    line, environment = command.harness_line("codex", Path("/w"))

    assert line.endswith("check_for_update_on_startup=false")
    assert environment == {}


def test_only_a_codex_on_the_shared_daemon_is_unclaimable():
    assert "--no-daemon" in command.unclaimable("codex -m gpt")
    assert command.unclaimable("codex --no-daemon") == ""
    assert command.unclaimable("claude --remote-control") == ""


def test_only_a_one_command_line_drops_the_prompt_from_the_harness_environment():
    """`env -u` in front of `a && b` would wrap only `a`."""
    compound, _ = command.harness_line("lemonaid claude patch && claude", Path("/w"), "go")

    assert compound == 'lemonaid claude patch && claude "$LEMONAID_PROMPT"'
    assert (
        command.harness_line("setup\nclaude", Path("/w"), "go")[0]
        == 'setup\nclaude "$LEMONAID_PROMPT"'
    )
