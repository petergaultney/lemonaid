"""The Needs ask in a brief, normalized for comparison."""

import re

_ASK_HEADING = re.compile(r"^#{3,6}\s+\**Needs(?:\s+\w+)?\**\s*:?\s*#*\s*$", re.I)
_ASK_BULLET = re.compile(r"^([ \t]*)[-*+]\s+\**Needs(?:\s+\w+)?\**\s*:\**(.*)$", re.I)
_HEADING = re.compile(r"^#{1,6}\s")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+")


def needs(text: str) -> str:
    """The first Needs section, with whitespace and bullet formatting normalized."""
    lines: list[str] = []
    active = False
    indent: int | None = None
    fence = ""
    for line in text.splitlines():
        delimiter = _FENCE.match(line)
        if not fence:
            if active:
                if _HEADING.match(line) or (
                    indent is not None
                    and line.strip()
                    and len(line.expandtabs()) - len(line.expandtabs().lstrip()) <= indent
                ):
                    break
            elif _ASK_HEADING.fullmatch(line):
                active = True
                continue
            elif bullet := _ASK_BULLET.fullmatch(line):
                active = True
                indent = len(bullet[1].expandtabs())
                lines.append(bullet[2])
                continue
        if active:
            lines.append(_BULLET.sub("", line))
        if delimiter:
            if not fence:
                fence = delimiter[1]
            elif (
                delimiter[1][0] == fence[0]
                and len(delimiter[1]) >= len(fence)
                and not delimiter[2].strip()
            ):
                fence = ""

    collapsed = " ".join(" ".join(lines).split())
    return (
        ""
        if collapsed.rstrip(".").lower() in {"", "nothing", "none", "no", "n/a", "-"}
        else collapsed
    )
