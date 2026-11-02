"""A brief's `## Questions` entries, matched to the Needs bullets that ask them.

Each entry is a `###` heading under `## Questions`, named with the label of the
bullet it explains under the Needs heading (`### Needs`, or `### Needs <name>`).
A bullet's label is its text before a colon, or the whole bullet, so
`- render timeouts owner: who fixes it?` is explained by `### render timeouts owner`
or by the full text. Bold or italic markers and case are ignored; code spans are
kept as written.
"""

import dataclasses
import re
from collections import abc

_HEADING = re.compile(r"###\s+(?P<label>.+?)\s*#*\s*")
_TOP_LEVEL_BULLET = re.compile(r"[-*+]\s+(?P<text>.*)")
_CODE_SPAN = re.compile(r"(`+)(?P<code>.+?)\1")
_EMPHASIS = re.compile(r"\*+|(?<!\w)_+|_+(?!\w)")  # intraword underscores are not emphasis
_MD_LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?:<[^>]*>|[^)]*)\)")
_SPACES = re.compile(r"\s+")
_LEAD = re.compile(r":(?:\s|$)")


@dataclasses.dataclass(frozen=True)
class Item:
    text: str  # Markdown: the bullet without its marker, its sub-bullets indented under it
    label: str = ""  # the heading of the entry that explains it, or "" for none
    entry: str = ""  # Markdown: that entry's body


def entries(questions: str) -> dict[str, str]:
    """Each entry's heading to its body, in order, from the text of `## Questions`."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in questions.splitlines():
        if heading := _HEADING.fullmatch(line):
            current = found.setdefault(heading["label"], [])
            continue

        if current is not None:
            current.append(line)

    return {label: "\n".join(lines).strip() for label, lines in found.items()}


def _segments(text: str) -> abc.Iterator[tuple[str, bool]]:
    """*text* in pieces, each with whether it is a code span (backticks included)."""
    end = 0
    for span in _CODE_SPAN.finditer(text):
        yield text[end : span.start()], False
        yield span[0], True
        end = span.end()

    yield text[end:], False


def _unmarked(text: str) -> str:
    """*text* without emphasis markers or repeated spaces, its code spans left as written."""
    return "".join(
        piece if code else _SPACES.sub(" ", _EMPHASIS.sub("", piece))
        for piece, code in _segments(text)
    ).strip()


def _plain(text: str) -> str:
    unlinked = _MD_LINK.sub(r"\g<text>", text)
    return " ".join(_CODE_SPAN.sub(r"\g<code>", _unmarked(unlinked)).split()).casefold()


def _lead(text: str) -> str:
    """*text* up to its first colon outside a code span that ends a word, or all of it."""
    done = 0
    for piece, code in _segments(text):
        if not code and (colon := _LEAD.search(piece)):
            return text[: done + colon.start()].strip()

        done += len(piece)

    return text


def _explains(label: str, bullet: str) -> bool:
    plain_label, plain_bullet = _plain(label), _plain(bullet.splitlines()[0])
    return bool(plain_label) and (
        plain_bullet == plain_label or plain_bullet.startswith(f"{plain_label}:")
    )


def _bullets(needs: str) -> abc.Iterator[str]:
    """Each top-level item of Needs with its continuation lines; a paragraph is one item."""
    lines: list[str] = []
    for line in needs.splitlines():
        if (bullet := _TOP_LEVEL_BULLET.fullmatch(line)) and lines:
            yield "\n".join(lines).strip()
            lines = []
        lines.append(bullet["text"] if bullet else line)

    if any(line.strip() for line in lines):
        yield "\n".join(lines).strip()


def _item(
    text: str, explained: abc.Mapping[str, str], linked: abc.Callable[[str], str | None]
) -> Item:
    """The `## Questions` entry that explains *text*, else the section it links to."""
    for label, entry in explained.items():
        if _explains(label, text):
            return Item(text, label, entry)

    section = linked(text)
    return (
        Item(text)
        if section is None
        else Item(text, _MD_LINK.sub(r"\g<text>", labels_of(text)), section)
    )


def items(
    needs: str,
    explained: abc.Mapping[str, str],
    linked: abc.Callable[[str], str | None] = lambda text: None,
) -> tuple[Item, ...]:
    """Needs as items, each with its entry or linked section; () when none has one."""
    found = tuple(_item(text, explained, linked) for text in _bullets(needs))
    return found if any(item.label for item in found) else ()


def labels_of(bullet: str) -> str:
    return _lead(_unmarked(bullet.splitlines()[0]))


def unmatched(needs: str, explained: abc.Mapping[str, str]) -> tuple[str, ...]:
    """Question headings with no corresponding Needs bullet, in document order."""
    bullets = tuple(_bullets(needs))
    return tuple(
        label for label in explained if not any(_explains(label, bullet) for bullet in bullets)
    )


def labels(needs: str, without: str = "") -> list[str]:
    """Each Needs bullet's label, leaving out the bullet the label *without* explains."""
    return [
        labels_of(bullet)
        for bullet in _bullets(needs)
        if not (without and _explains(without, bullet))
    ]


def answer(label: str, text: str) -> str:
    return f"Answer to {label}: {text}"


def more_detail(label: str) -> str:
    return f"More detail needed on {label}: rewrite that entry in ## Questions"
