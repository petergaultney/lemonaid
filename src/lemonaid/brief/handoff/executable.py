"""Find the Claude or Codex executable a launch command line actually runs."""

import re
import typing as ty

_OPERATORS = "&|;()"
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# Per wrapper: options taking an argument, and options that don't. Any other option
# (`--help`, `-S`, `command -v`) means the wrapper does not launch the command that follows.
_ARG_OPTIONS = {"env": ("-u", "-C"), "command": (), "exec": ("-a",)}
_FLAG_OPTIONS = {
    "env": ("-i", "-0", "-v", "--ignore-environment", "--null", "--debug"),
    "command": ("-p",),
    "exec": ("-c", "-l"),
}


class _Word(ty.NamedTuple):
    raw: str
    value: str


def _segments(line: str) -> list[list[_Word]]:
    """Split `line` into words per `&&`/`;`/`|` command, honoring quotes and backslashes."""
    segments: list[list[_Word]] = [[]]
    raw = value = ""
    quote = ""
    escaped = False
    started = False

    def end_word() -> None:
        nonlocal raw, value, started
        if started:
            segments[-1].append(_Word(raw, value))
        raw = value = ""
        started = False

    for char in line:
        if escaped:
            raw, value, escaped = raw + char, value + char, False
        elif char == "\\" and quote != "'":
            raw, escaped, started = raw + char, True, True
        elif quote:
            raw += char
            if char == quote:
                quote = ""
            else:
                value += char
        elif char in "'\"":
            raw, quote, started = raw + char, char, True
        elif char in _OPERATORS:
            end_word()
            segments.append([])
        elif char.isspace():
            end_word()
        else:
            raw, value, started = raw + char, value + char, True

    end_word()

    return segments


def _command_words(words: list[_Word]) -> list[_Word]:
    """`words` without leading assignments and wrappers; empty if the wrapper can't launch."""
    while words:
        wrapper = words[0].value
        if _ASSIGNMENT.match(words[0].raw):
            words = words[1:]
        elif wrapper in _ARG_OPTIONS:
            words = words[1:]
            while words and words[0].value.startswith("-"):
                option = words[0].value
                if option == "--":
                    words = words[1:]
                    break

                if option in _ARG_OPTIONS[wrapper]:
                    words = words[2:]
                elif option in _FLAG_OPTIONS[wrapper] or option.startswith(
                    ("--unset=", "--chdir=")
                ):
                    words = words[1:]
                else:
                    return []

            while wrapper == "env" and words and "=" in words[0].value:
                words = words[1:]
        else:
            break

    return words


def harness_executable(line: str) -> str:
    """The first `claude`/`codex` executable launched by any command in `line`, else "".

    Wrapper options outside a small known set mean nothing is launched.
    """
    for words in _segments(line):
        if (command := _command_words(words)) and (
            backend := command[0].value.rsplit("/", 1)[-1]
        ) in ("claude", "codex"):
            return backend

    return ""
