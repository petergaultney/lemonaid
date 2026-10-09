"""The shell line that starts a lemon: a template's harness command, set up to start unattended.

Codex asks whether to trust a directory it hasn't seen, and whether to update,
before it reads a prompt, and a prompt passed as an argument is lost behind
those dialogs. Both are answered with `-c` overrides rather than keystrokes;
nothing is written to Codex's own config.
"""

import json
import shlex
from collections import abc
from pathlib import Path

from ..config import TmuxSessionConfig
from ..inbox import db
from ..tmux import navigation

PROMPT_VARIABLE = "LEMONAID_PROMPT"


def template_window(config: TmuxSessionConfig, windows: list[str]) -> int:
    """The 0-based position in *windows* of the template's harness window."""
    configured = config.resume_window if config.harness_window is None else config.harness_window
    return max(0, min(configured, len(windows) - 1))


def codex_writable_roots(config: TmuxSessionConfig) -> list[Path]:
    """What a sandboxed Codex lemon needs to write for `lemonaid tell` and brief
    commands: the inbox database's directory and the state directory, plus the
    configured `codex_writable_roots`."""
    return [db.get_db_path().parent, navigation.get_state_path(), *config.codex_writable_roots]


def _codex_flags(directory: Path, writable: abc.Iterable[Path]) -> list[str]:
    roots = list(dict.fromkeys(str(r) for r in writable))
    return [
        "-c",
        f'projects={{{json.dumps(str(directory), ensure_ascii=False)}={{trust_level="trusted"}}}}',
        "-c",
        "check_for_update_on_startup=false",
        *(
            [
                "-c",
                f"sandbox_workspace_write.writable_roots={json.dumps(roots, ensure_ascii=False)}",
            ]
            if roots
            else []
        ),
    ]


def _is_codex(words: list[str]) -> bool:
    return bool(words) and Path(words[0]).name == "codex"


def unclaimable(line: str) -> str:
    """Why a brief waiting on a window can't reach the lemon *line* starts, or "".

    A Codex on the shared app-server reports no pane, so no inbox row says it
    is the one in the window.
    """
    words = shlex.split(line)
    if _is_codex(words) and "--no-daemon" not in words:
        return f"{line!r} runs Codex on the shared app-server, which can't be matched to its window to claim a brief; add --no-daemon to the template"

    return ""


def _is_simple(line: str) -> bool:
    """Whether *line* is one command, with no operator or newline joining or redirecting it."""
    lexer = shlex.shlex(line.strip(), posix=True, punctuation_chars=True)
    return "\n" not in line.strip() and not any(set(token) <= set("();<>|&") for token in lexer)


def harness_line(
    line: str, directory: Path, prompt: str = "", writable: abc.Iterable[Path] = ()
) -> tuple[str, dict[str, str]]:
    """*line* with the flags its harness needs to start in *directory*, and the
    environment the line's shell must be started with.

    The line is typed into the user's shell, whose quoting rules lemonaid doesn't
    know, so the prompt goes through the environment: `"$VAR"` is one word to a
    POSIX shell, fish, and xonsh alike, whatever the prompt contains.

    A Codex line also gets *writable* as extra workspace-write sandbox roots; they
    have no effect under another sandbox mode.
    """
    program, _, rest = line.strip().partition(" ")
    if _is_codex(shlex.split(program)):
        line = " ".join(
            [program, *(shlex.quote(f) for f in _codex_flags(directory, writable)), rest]
        ).strip()

    if not prompt:
        return line, {}

    # The shell expands the argument before `env` drops the variable, so the
    # harness's own children never see it. A compound line (`a && b`) would only
    # have its first command wrapped, so it is left as is.
    wrapped = f"env -u {PROMPT_VARIABLE} {line}" if _is_simple(line) else line
    return f'{wrapped} "${PROMPT_VARIABLE}"', {PROMPT_VARIABLE: prompt}
