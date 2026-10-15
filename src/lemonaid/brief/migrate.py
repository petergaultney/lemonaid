"""Explicitly promote the four legacy progress headings without changing their bodies."""

from . import sections


def layout(text: str) -> str:
    old = [
        h
        for h in sections.scan(text)
        if h.level == 3 and h.parent.lower() == "now" and h.name.lower() in sections.PROMOTED
    ]
    for heading in old:
        sections.find(text, heading.name)  # refuse collisions before changing anything
    if not old:
        return text
    source = text.splitlines()
    metadata = sections.metadata_indices(text)
    blocks = [line for h in old for line in [f"## {h.name}", *sections.body(text, h), ""]]
    for h in reversed(old):
        source[h.start : h.end] = [
            text.splitlines()[i] for i in range(h.start, h.end) if i in metadata
        ]
    remaining = "\n".join(source) + "\n"
    headings = sections.scan(remaining)
    questions = next((h for h in headings if h.level == 2 and h.name.lower() == "questions"), None)
    now = sections.find(remaining, "Now")
    at = questions.end if questions else now.end if now else len(source)
    source[at:at] = ["", *blocks, ""]
    return "\n".join(source).rstrip() + "\n"
