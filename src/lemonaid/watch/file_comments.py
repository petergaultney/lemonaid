"""The doc waiter's view of comment threads kept in the file (`lemonaid.comments`).

A Python or Markdown file with a threads section is read with that model. Every doc but a
Python file is also read for Relay and plain CriticMarkup threads, so a person can comment
either way in the same file; in Python that markup is code.
"""

import hashlib
import pathlib
import re
import typing as ty

from ..comments import edits, kinds, model, parse, threads
from . import clip, relay_comments

KEY_PREFIX: ty.Final = "lma:"
_LINE_END: ty.Final = re.compile(r"\r\n|\r")


def read(doc: pathlib.Path) -> str:
    """The doc's text with its line endings as they are, as `lemonaid comments` reads it, so
    both find the same section."""
    with doc.open(encoding="utf-8", newline="") as f:
        return f.read()


def _kind(doc: pathlib.Path) -> model.FileKind | None:
    """The kind of the file `doc` names, as `lemonaid comments` decides it: a link
    `notes.md` to `code.py` is Python."""
    return model.file_kind(str(doc.resolve()))


def document(doc: pathlib.Path, text: str) -> model.Document | None:
    """The parsed file, when it is a kind that holds comments and has a threads section."""
    kind = _kind(doc)
    if kind is None:
        return None

    parsed = parse.parse(text, kind)
    return parsed if parsed.section is not None else None


def body(doc: pathlib.Path, text: str) -> str:
    """What a person wrote, with LF line endings: in-file comments and, outside Python, Relay
    blocks both removed, whichever the waiter reads for threads, so adding the first in-file
    comment or stripping the last never reads as an edit. Relay is Markdown markup, so in
    Python its shape is code, and editing it is an edit.

    Unlike `strip`, this removes every marker a root comment owns even when the file has
    two of them or they are reversed: the body is only compared, never written back.
    """
    kind = _kind(doc)
    parsed = parse.parse(text, kind) if kind is not None else None
    if parsed is not None and (parsed.section is not None or parsed.markers):
        root_ids = {c.id for c in parsed.comments if c.re is None}
        removed = [model.Edit(*m.carrier, "") for m in parsed.markers if m.id in root_ids]
        if parsed.section is not None:
            removed.append(model.Edit(parsed.section.start, parsed.section.end, ""))
        text = edits.apply(text, removed)
    lf_text = _LINE_END.sub("\n", text)
    if kind == "python":
        return lf_text
    return relay_comments.body_without_threads(lf_text, _code(kind, lf_text))


def relay_text(doc: pathlib.Path, text: str) -> tuple[str, relay_comments.Regions] | None:
    """The text to read Relay and plain CriticMarkup threads in, with LF line endings, and
    its Markdown code regions, where a doc quotes that markup as an example. None for
    Python, where that markup is code. The threads section needs no special case: records
    escape `>`, so `{>>` and `>>...<<}}` never appear in one."""
    kind = _kind(doc)
    if kind == "python":
        return None

    lf_text = _LINE_END.sub("\n", text)
    return lf_text, _code(kind, lf_text)


def _code(kind: model.FileKind | None, lf_text: str) -> relay_comments.Regions:
    if kind != "markdown":
        return ()
    return [(r.start, r.end) for r in kinds.get("markdown").code_regions(lf_text)]


def unanswered(parsed: model.Document, mine: ty.AbstractSet[str]) -> list[model.Comment]:
    return threads.unanswered(parsed, mine)


def key(comment: model.Comment) -> str:
    """A reported comment's cursor key: its id, and a digest of what it says, since an id can
    be used again once the file is stripped. The prefix keeps it apart from Relay threads'
    digests."""
    record = "\0".join([comment.re or "", comment.author, comment.at, comment.body])
    return f"{KEY_PREFIX}{comment.id}:{hashlib.sha1(record.encode()).hexdigest()[:12]}"


def id_of(key: str) -> str:
    return key.removeprefix(KEY_PREFIX).rpartition(":")[0]


def comment_text(comment: model.Comment) -> str:
    about = f"re {comment.re}" if comment.re else "new thread"
    return f"{comment.author} [{comment.id}, {about}]:\n" + clip.shorten(
        comment.body.strip(), clip.COMMENT_LIMIT
    )


def comment_gist(comment: model.Comment) -> str:
    return f"{comment.author} [{comment.id}]: {comment.body.strip().replace(chr(10), ' ')[:100]}"


def how_to_answer(doc: pathlib.Path, ids: ty.Iterable[str]) -> str:
    """Kept ahead of the comments' text, so a wake cut to the batch limit still has it."""
    return (
        f"Ids: {', '.join(ids)}. Read them with their code: lemonaid comments list {doc}"
        f" --unanswered --self. Answer each with lemonaid comments reply {doc} --re <id>"
        " --self <body>. If someone replied first, the reply is refused and shows what they"
        " wrote: add only what they didn't say, with the --after it names, or nothing."
    )
