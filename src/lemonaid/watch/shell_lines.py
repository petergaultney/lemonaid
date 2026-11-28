"""Where a shell command's lines of shell are, and the simple commands on them.

A newline inside quotes doesn't end a line, so a quoted commit message can run over
several. A heredoc's body is text, not shell, so it is on no line. When a quote never
closes, every newline ends a line.
"""

import re
import shlex
from collections import abc

_WORD_START = frozenset(" \t\n;&|()")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*([^\s;&|()<>]+)")
_SEPARATORS = frozenset({";", "|", "||", "&&", "&"})


def _body_end(command: str, at: int, delimiter: str, tabs: bool) -> int:
    """Where *command* goes on after the heredoc body that starts at *at*."""
    while at < len(command):
        end = command.find("\n", at)
        end = len(command) if end == -1 else end
        line = command[at:end].rstrip("\r")
        at = end + 1
        if (line.lstrip("\t") if tabs else line) == delimiter:
            break
    return min(at, len(command))


def _physical(command: str) -> list[tuple[int, int]]:
    newlines = [m.start() for m in re.finditer("\n", command)]
    return list(zip([0, *(n + 1 for n in newlines)], [*newlines, len(command)], strict=True))


def spans(command: str) -> list[tuple[int, int]]:
    """The start and end of each line of shell in *command*."""
    found, start, quote, at, heredocs = [], 0, "", 0, []
    while at < len(command):
        char = command[at]
        if char == "\\" and quote != "'":
            at += 2  # the escaped character, a newline too, stays on this line
            continue

        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (at == 0 or command[at - 1] in _WORD_START):
            end = command.find("\n", at)
            at = len(command) if end == -1 else end
            continue
        elif char == "<" and (heredoc := _HEREDOC.match(command, at)):
            heredocs.append((re.sub(r"[\\'\"]", "", heredoc[2]), heredoc[1] == "-"))
            at = heredoc.end()
            continue
        elif char == "\n":
            found.append((start, at))
            start = at + 1
            for delimiter, tabs in heredocs:
                start = _body_end(command, start, delimiter, tabs)
            heredocs, at = [], start
            continue
        at += 1

    return _physical(command) if quote else [*found, (start, len(command))]


def segments(command: str) -> abc.Iterator[list[str]]:
    """The shell words of each simple command in *command*; quoted text stays one word."""
    for start, end in spans(command):
        lexer = shlex.shlex(command[start:end], posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            words = list(lexer)
        except ValueError:  # unbalanced quotes
            continue
        segment: list[str] = []
        for word in [*words, ";"]:
            if word in _SEPARATORS:
                yield segment
                segment = []
            else:
                segment.append(word)
