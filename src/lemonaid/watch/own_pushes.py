"""Heads a lemon pushed, so its own `watch pr` waiter does not wake it for them.

GitHub can't say who pushed, since every lemon pushes under its human's account. The
after-tool hook reads a shell call's output instead: `git push` prints one
`<old>..<new>  <src> -> <dst>` line per updated ref (`...` and a leading `+` when
forced). Each `<new>` it finds is kept, newest last, in `<writer dir>/pushes`.
"""

import itertools
import pathlib
import re
import shlex
from collections import abc

from . import own_edits

_KEEP = 50
_UPDATED_REF = re.compile(
    r"^\s*\+?\s*[0-9a-f]{7,40}\.\.\.?([0-9a-f]{7,40})\s+\S+\s+->\s+\S+", re.MULTILINE
)
_PUSH_COMMAND = re.compile(r"\bgit(?:\s+-[Cc]\s+\S+|\s+-{1,2}[\w-]+(?:=\S+)?)*\s+push\b")


def is_push(command: str) -> bool:
    return bool(_PUSH_COMMAND.search(command))


_SEPARATORS = frozenset({";", "|", "||", "&&", "&"})
_QUIET_FLAG = re.compile(r"--quiet|-[A-Za-z]*q[A-Za-z]*")


def _segments(command: str) -> abc.Iterator[list[str]]:
    """The shell words of each simple command in *command*; quoted text stays one word."""
    for line in command.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
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


def _hides_stderr(words: list[str]) -> bool:
    """`2>/dev/null`, `&>/dev/null`, or `>/dev/null 2>&1`, as `shlex` splits them."""
    pairs = set(itertools.pairwise(words))
    triples = set(zip(words, words[1:], words[2:], strict=False))
    return (
        ("2", ">", "/dev/null") in triples
        or ("&>", "/dev/null") in pairs
        or ((">", "/dev/null") in pairs and ("2", ">&", "1") in triples)
    )


def hides_heads(command: str) -> bool:
    """Whether a `git push` in *command* prints no updated refs: it is quiet, or its stderr,
    where git prints them, goes to /dev/null."""
    for words in _segments(command):
        if "git" not in words or "push" not in words[words.index("git") :]:
            continue

        after = words[words.index("push", words.index("git")) + 1 :]
        if _hides_stderr(after) or any(_QUIET_FLAG.fullmatch(word) for word in after):
            return True

    return False


_SEGMENT_END = re.compile(r";|\|\|?|&&|\n")
_QUIET_WORD = re.compile(r"[ \t]+(?:--quiet|-([A-Za-z]*)q([A-Za-z]*))(?=[ \t]|$)")


def _without_quiet(word: str) -> str:
    """A push option with its `q` taken out: "" for `-q` or `--quiet`, `-u` for `-qu`."""
    if word == "--quiet":
        return ""

    return "-" + word[1:].replace("q", "", 1) if _QUIET_FLAG.fullmatch(word) else word


def _expected(words: list[str]) -> list[str]:
    """*words* as they should be once each `git push` stops being quiet."""
    if "git" not in words or "push" not in words[words.index("git") :]:
        return words

    at = words.index("push", words.index("git")) + 1
    return [*words[:at], *filter(lambda w: w not in ("", "-"), map(_without_quiet, words[at:]))]


def loud(command: str) -> str | None:
    """*command* with each `git push`'s `-q`/`--quiet` removed, so it prints its heads; None
    when that isn't enough (stderr sent to /dev/null) or would change any other word."""
    segments = list(_segments(command))
    if any(
        _hides_stderr(words[words.index("push", words.index("git")) + 1 :])
        for words in segments
        if "git" in words and "push" in words[words.index("git") :]
    ):
        return None

    def drop(match: re.Match[str]) -> str:
        rest = (match[1] or "") + (match[2] or "")
        return f" -{rest}" if rest else ""

    pieces, at = [], 0
    for match in _PUSH_COMMAND.finditer(command):
        found = _SEGMENT_END.search(command, match.end())
        end = found.start() if found else len(command)
        pieces += [command[at : match.end()], _QUIET_WORD.sub(drop, command[match.end() : end])]
        at = end
    rewritten = "".join([*pieces, command[at:]])
    return rewritten if list(_segments(rewritten)) == [_expected(w) for w in segments] else None


def heads_in(output: str) -> list[str]:
    return [m.group(1).lower() for m in _UPDATED_REF.finditer(output)]


def _path(own_root: pathlib.Path, writer: str) -> pathlib.Path:
    return own_edits.writer_dir(own_root, writer) / "pushes"


def _recorded(own_root: pathlib.Path, writer: str) -> list[str]:
    try:
        return _path(own_root, writer).read_text().split()
    except FileNotFoundError:
        return []


def register(own_root: pathlib.Path, writer: str) -> None:
    """Make the writer's directory, which is what lets the installed hook start Python."""
    own_edits.writer_dir(own_root, writer).mkdir(parents=True, exist_ok=True)


def record(own_root: pathlib.Path, writer: str, heads: abc.Iterable[str]) -> None:
    heads = list(heads)
    if not heads:
        return

    path = _path(own_root, writer)
    with own_edits.locked(path):
        path.write_text("".join(f"{h}\n" for h in [*_recorded(own_root, writer), *heads][-_KEEP:]))


def is_own(own_root: pathlib.Path, writer: str, head: str) -> bool:
    """Whether `head` (a full SHA) is one the writer's recorded pushes abbreviate."""
    return bool(writer) and any(head.startswith(h) for h in _recorded(own_root, writer))
