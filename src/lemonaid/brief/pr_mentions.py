"""The pull requests a brief links to, which lemonaid asks about when they merge or close.

Only URLs count, since a bare `#N` names no repository. A PR linked under a `No nudge`
heading, at any level, is never asked about, wherever else the brief links it.
"""

from collections import abc

from . import pr, sections

NO_NUDGE = "No nudge"


def _targets(lines: abc.Iterable[str]) -> set[tuple[str, str]]:
    return {found for line in lines for url in pr.urls(line) if (found := pr.repo_and_number(url))}


def nudged(text: str) -> set[tuple[str, str]]:
    """(`owner/repo`, number) of each PR the brief links outside code fences and `No nudge`."""
    lines = dict(sections.unfenced_lines(text))
    quiet = {
        i
        for heading in sections.scan(text)
        if heading.name.casefold() == NO_NUDGE.casefold()
        for i in range(heading.start, heading.end)
    }
    return _targets(line for i, line in lines.items() if i not in quiet) - _targets(
        lines[i] for i in quiet if i in lines
    )
