"""`lemonaid lsp`: the language server an editor starts over stdio for review comments.

It parses each open Python and Markdown document on every change, publishes a diagnostic
at each anchor and format error, and sends `lemonaid/threads` when a document's comments
change. Editor commands (`lemonaid.comment`, `lemonaid.reply`, `lemonaid.resolve`) come
back as `workspace/applyEdit`, so only the server inserts anchors and appends records.

    documents   the server and its open documents
    sync        whether a buffer and its file still agree
    editing     sending an edit to the editor and waiting for it to show
    bridge      the socket lemons reach the server through
"""

import asyncio
import typing as ty

from lsprotocol import types

from .. import config
from ..comments import edits, model, operations, parse
from . import bridge, documents, editing, positions, publish, sync
from .documents import CommentsServer, Refused

THREADS: ty.Final = "lemonaid/threads"
COMMENT: ty.Final = "lemonaid.comment"
REPLY: ty.Final = "lemonaid.reply"
RESOLVE: ty.Final = "lemonaid.resolve"


def build() -> CommentsServer:
    server = CommentsServer()

    @server.feature(types.INITIALIZED)
    async def initialized(ls: CommentsServer, _: types.InitializedParams) -> None:
        await bridge.start(ls)

    @server.feature(types.SHUTDOWN)
    def shutdown(ls: CommentsServer, _: None) -> None:
        bridge.stop(ls)

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: CommentsServer, params: types.DidOpenTextDocumentParams) -> None:
        ls.forget(params.text_document.uri)
        _refresh(ls, params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: CommentsServer, params: types.DidChangeTextDocumentParams) -> None:
        _refresh(ls, params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(ls: CommentsServer, params: types.DidSaveTextDocumentParams) -> None:
        if (document := documents.managed(ls, params.text_document.uri)) is not None:
            sync.note(ls, document)

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(ls: CommentsServer, params: types.DidCloseTextDocumentParams) -> None:
        ls.forget(params.text_document.uri)
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=params.text_document.uri, diagnostics=[])
        )

    @server.command(COMMENT)
    async def comment(ls: CommentsServer, *arguments: ty.Any) -> dict[str, ty.Any]:
        """Arguments: `{uri, range, body}`. Anchors a thread on the range."""
        uri, body = _argument(arguments, "uri", str), _argument(arguments, "body", str)
        lsp_range = _argument(arguments, "range", dict)
        author = config.load_config().comments.signature()

        def change(text: str, kind: model.FileKind, comment_id: str | None) -> editing.Change:
            codec = documents.codec(ls, text)
            start, end = (codec.offset(_position(lsp_range, end)) for end in ("start", "end"))
            added = edits.add_comment(
                text, kind, start, end, author=author, body=body, comment_id=comment_id
            )
            return editing.Change(
                added.edits, added.comment_id, editing.has_comment(kind, added.comment_id)
            )

        document = documents.open_by_uri(ls, uri)
        return {"id": await editing.apply(ls, document, change, retry=False)}

    @server.command(REPLY)
    async def reply(ls: CommentsServer, *arguments: ty.Any) -> dict[str, ty.Any]:
        """Arguments: `{uri, re, body, span?}`, `span` a `[start, end]` range of characters in
        the body of the comment `re` names."""
        uri, body = _argument(arguments, "uri", str), _argument(arguments, "body", str)
        re_ = _argument(arguments, "re", str)
        span = _span(arguments[0].get("span") if arguments else None)
        author = config.load_config().comments.signature()

        def change(text: str, kind: model.FileKind, comment_id: str | None) -> editing.Change:
            added = edits.reply(
                text, kind, re_, author=author, body=body, span=span, comment_id=comment_id
            )
            return editing.Change(
                added.edits, added.comment_id, editing.has_comment(kind, added.comment_id)
            )

        return {"id": await editing.apply(ls, documents.open_by_uri(ls, uri), change)}

    @server.command(RESOLVE)
    async def resolve(ls: CommentsServer, *arguments: ty.Any) -> dict[str, ty.Any]:
        """Arguments: `{uri, id}`."""
        uri, comment_id = _argument(arguments, "uri", str), _argument(arguments, "id", str)
        operation = operations.Resolve(comment_id, config.load_config().comments.signature())
        change = editing.operation_change(operation, edits.now())
        await editing.apply(ls, documents.open_by_uri(ls, uri), change)
        return {}

    return server


def _refresh(ls: CommentsServer, uri: str) -> None:
    document = documents.managed(ls, uri)
    if document is None or (kind := documents.kind(document)) is None:
        return
    sync.note(ls, document)
    key = documents.key(document.uri)
    doc = parse.parse(document.source, kind)
    codec = documents.codec(ls, document.source)
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(
            uri=document.uri, version=document.version, diagnostics=publish.diagnostics(doc, codec)
        )
    )
    threads_key = publish.threads_key(doc)
    if ls.sent_keys.get(key) != threads_key:
        ls.sent_keys[key] = threads_key
        ls.protocol.notify(
            THREADS, publish.threads_params(document.uri, document.version, doc, codec)
        )
    ls.changed.setdefault(key, asyncio.Event()).set()


_Field = ty.TypeVar("_Field")


def _argument(arguments: tuple[ty.Any, ...], name: str, of_type: type[_Field]) -> _Field:
    value = arguments[0].get(name) if arguments and isinstance(arguments[0], dict) else None
    if not isinstance(value, of_type):
        raise Refused(f"the command needs `{name}`")
    return value


def _position(lsp_range: dict[str, ty.Any], end: str) -> positions.Position:
    point = lsp_range.get(end)
    if not isinstance(point, dict):
        raise Refused(f"the range needs `{end}`")
    return positions.Position(int(point["line"]), int(point["character"]))


def _span(raw: object) -> tuple[int, int] | None:
    if raw is None:
        return None
    if not (isinstance(raw, list) and len(raw) == 2 and all(isinstance(n, int) for n in raw)):
        raise Refused("`span` is `[start, end]`")
    return raw[0], raw[1]


def main() -> None:
    build().start_io()
