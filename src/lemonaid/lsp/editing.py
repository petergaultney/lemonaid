"""Editing an open buffer: send the edit, then wait until it shows in the document."""

import asyncio
import contextlib
import time
import typing as ty
from collections import abc

from lsprotocol import types
from pygls.workspace import TextDocument

from ..comments import model, operations, parse
from . import documents, positions, registry, sync
from .documents import CommentsServer, Refused

_ATTEMPTS: ty.Final = 3
# How long we wait for the editor's change notification after it applies our edit. nvim
# batches changes for 150 ms before it sends them.
_LANDING_SECONDS: ty.Final = 3.0

_MOVED: ty.Final = (
    "your buffer changed while we wrote the comment, so its lines may name other code now;"
    " check them and try again"
)


class Change(ty.NamedTuple):
    """An edit to make, the result to return, and how to tell it reached the document."""

    edits: list[model.Edit]
    result: str | None
    landed: abc.Callable[[str], bool]


_Planner = abc.Callable[[str, model.FileKind, str | None], Change]


async def apply(
    ls: CommentsServer,
    document: TextDocument,
    change: _Planner,
    *,
    retry: bool = True,
    observed: str | None = None,
) -> str | None:
    """Compute the change against `document` as the server has it and send it to the
    editor, versioned, so an editor whose buffer has moved on rejects it. Some editors
    (nvim) report a rejected edit as applied, so we wait until the edit shows in the
    document, and compute it again from what the document holds if it doesn't. A retry
    keeps the comment's id and time, so an edit that arrives late isn't written twice.

    With `observed`, the digest (`registry.text_digest`) of the text the caller chose its
    lines from, we refuse if the buffer has changed since. We stop once the editor closes
    the document, since what pygls would give us then is the file, without a version, and
    before each send once the file has moved past what the buffer last shared with it
    (`sync.disk_moved`), for editor commands and lemons alike.
    """
    kind = documents.kind(document)
    if kind is None:
        raise Refused(f"{document.uri} is not a Python or Markdown document")
    if observed is not None and registry.text_digest(document.source) != observed:
        raise Refused(_MOVED)
    comment_id = None
    for _ in range(_ATTEMPTS):
        if documents.managed(ls, document.uri) is not document:
            raise Refused("the editor closed the file before the comment was written")
        text, version = document.source, document.version
        try:
            planned = change(text, kind, comment_id)
        except ValueError as refusal:
            if comment_id is not None and has_comment(kind, comment_id)(text):
                return comment_id
            raise Refused(str(refusal)) from None
        comment_id = planned.result
        if not planned.edits or planned.landed(text):
            return planned.result
        if sync.disk_moved(ls, document):
            raise Refused(sync.DIVERGED)
        codec = documents.codec(ls, text)
        answer = await ls.workspace_apply_edit_async(
            types.ApplyWorkspaceEditParams(
                label="lemonaid comments",
                edit=types.WorkspaceEdit(
                    document_changes=[
                        types.TextDocumentEdit(
                            text_document=types.OptionalVersionedTextDocumentIdentifier(
                                uri=document.uri, version=version
                            ),
                            edits=[_text_edit(codec, edit) for edit in planned.edits],
                        )
                    ]
                ),
            )
        )
        if answer.applied and await _lands(ls, document, planned.landed):
            return planned.result
        if not retry:
            raise Refused(_MOVED)
    raise Refused(f"the editor didn't take the edit; tried {_ATTEMPTS} times")


def operation_change(operation: operations.Operation, at: str) -> _Planner:
    def change(text: str, kind: model.FileKind, comment_id: str | None) -> Change:
        planned, result = operations.edits_for(operation, text, kind, at=at, comment_id=comment_id)
        return Change(
            planned,
            result,
            lambda now: operations.landed(operation, now, kind, at=at, comment_id=result),
        )

    return change


def has_comment(kind: model.FileKind, comment_id: str) -> abc.Callable[[str], bool]:
    return lambda text: parse.parse(text, kind).comment(comment_id) is not None


async def _lands(
    ls: CommentsServer, document: TextDocument, landed: abc.Callable[[str], bool]
) -> bool:
    """Whether the edit shows in `document` before the wait is over or the editor closes it."""
    deadline = time.monotonic() + _LANDING_SECONDS
    event = ls.changed.setdefault(documents.key(document.uri), asyncio.Event())
    while documents.managed(ls, document.uri) is document:
        if landed(document.source):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        event.clear()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), remaining)
    return False


def _text_edit(codec: positions.Codec, edit: model.Edit) -> types.TextEdit:
    start, end = codec.position(edit.start), codec.position(edit.end)
    return types.TextEdit(
        range=types.Range(
            start=types.Position(line=start.line, character=start.character),
            end=types.Position(line=end.line, character=end.character),
        ),
        new_text=edit.text,
    )
