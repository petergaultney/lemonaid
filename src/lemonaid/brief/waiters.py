"""The edits to a brief's `## Waiters`: add, replace, or remove one waiter's command.

Each waiter is a bullet holding its command in backticks. Lines that aren't
bullets (a note on how to arm them) stay as written, and so does the rest of
the brief.
"""

import re
from collections import abc

_HEADING = re.compile(r"##\s+waiters\s*", re.IGNORECASE)
_SECTION = re.compile(r"#{1,2}\s")
_FENCE = re.compile(r"(```|~~~)")
_HEAD = re.compile(r"(--head(?:=|\s+))(<[^>]*>|\S+)")


class EditError(ValueError):
    pass


def _outside_fences(lines: abc.Sequence[str]) -> list[bool]:
    """Whether each line is outside a code fence, as `brief check` reads headings."""
    outside = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            outside.append(False)
        else:
            outside.append(not in_fence)
    return outside


def command_of(line: str) -> str | None:
    """The command a `## Waiters` bullet holds, or None for a line that isn't one."""
    if not line.startswith("- "):
        return None

    return line[2:].strip().strip("`").strip()


def _bullet(command: str) -> str:
    command = command.strip()
    if not command:
        raise EditError("The waiter's command is empty")

    if "\n" in command:
        raise EditError("A waiter's command is one line")

    ticks = "``" if "`" in command else "`"
    pad = " " if ticks == "``" else ""
    return f"- {ticks}{pad}{command}{pad}{ticks}"


def _with_body(text: str, change: abc.Callable[[list[str]], list[str]]) -> str:
    """*text* with the body of `## Waiters` replaced by *change* of it; a missing one goes last."""
    lines = text.rstrip("\n").splitlines()
    outside = _outside_fences(lines)
    start = next(
        (i for i, line in enumerate(lines) if outside[i] and _HEADING.fullmatch(line)), None
    )
    if start is None:
        return "\n".join([*lines, "", "## Waiters", *change([])]) + "\n"

    end = next(
        (i for i in range(start + 1, len(lines)) if outside[i] and _SECTION.match(lines[i])),
        len(lines),
    )
    body = change(lines[start + 1 : end])
    after = ["", *lines[end:]] if end < len(lines) else []
    while body and not body[-1].strip():
        body.pop()
    return "\n".join([*lines[: start + 1], *body, *after]) + "\n"


def _commands(body: abc.Sequence[str]) -> dict[int, str]:
    """The command of each waiter bullet in *body*, by line; bullets in a code fence are not."""
    outside = _outside_fences(body)
    return {
        i: command
        for i, line in enumerate(body)
        if outside[i] and (command := command_of(line)) is not None
    }


def _the_one(body: abc.Sequence[str], match: str) -> int:
    wanted = match.strip().lower()
    if not wanted:
        raise EditError("Name the waiter by part of its command")

    commands = _commands(body)
    found = [i for i, command in commands.items() if wanted in command.lower()]
    if len(found) == 1:
        return found[0]

    if not found:
        raise EditError(f"No waiter in ## Waiters contains {match!r}")

    shown = " | ".join(commands[i] for i in found)
    raise EditError(f"{len(found)} waiters contain {match!r}; use more of one: {shown}")


def add(text: str, command: str) -> str:
    """*text* with *command* listed under `## Waiters`; listing it again changes nothing."""
    line = _bullet(command)

    def change(body: list[str]) -> list[str]:
        commands = _commands(body)
        if command_of(line) in commands.values():
            return body

        if sum(1 for existing in body if _FENCE.match(existing)) % 2:
            raise EditError("## Waiters has a code fence that is never closed")

        last = max((i for i, existing in enumerate(body) if existing.strip()), default=-1)
        gap = [""] if last >= 0 and last not in commands else []
        return [*body[: last + 1], *gap, line, *body[last + 1 :]]

    return _with_body(text, change)


def with_head(command: str, head: str) -> str:
    """*command* passing `--head <head>`, replacing the head it passed, if any."""
    if not head.strip() or any(c.isspace() for c in head.strip()):
        raise EditError(f"{head!r} is not a head")

    if _HEAD.search(command):
        return _HEAD.sub(lambda m: m[1] + head.strip(), command, count=1)

    return f"{command} --head {head.strip()}"


def replace(text: str, match: str, command: str = "", head: str = "") -> str:
    """Replace the one waiter whose command contains *match*: with *command*, or a new *head*."""
    if not command and not head:
        raise EditError("Give the new command, or --head for the same waiter on a new head")

    def change(body: list[str]) -> list[str]:
        at = _the_one(body, match)
        new = command or command_of(body[at]) or ""
        return [*body[:at], _bullet(with_head(new, head) if head else new), *body[at + 1 :]]

    return _with_body(text, change)


def remove(text: str, match: str) -> str:
    def change(body: list[str]) -> list[str]:
        at = _the_one(body, match)
        return [*body[:at], *body[at + 1 :]]

    return _with_body(text, change)
