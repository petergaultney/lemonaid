"""The server, its open documents, and what it remembers about each.

pygls keys an open document by its uri percent-decoded (`key`), and we key our own state the
same way. Outgoing messages use the uri the editor sent, `document.uri`.
"""

import asyncio
import typing as ty
from pathlib import Path
from urllib.parse import unquote

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from ..comments import model
from . import positions, publish


class Refused(Exception):
    """What the server says no to, with the reason for the person or lemon who asked."""


class CommentsServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("lemonaid", "v1", text_document_sync_kind=types.TextDocumentSyncKind.Full)
        self.sent_keys: dict[str, publish.ThreadsKey] = {}
        # Set on each change, for an edit waiting to show in its document (`editing`).
        self.changed: dict[str, asyncio.Event] = {}
        # The buffer's text when it last matched the file, and the file's text then, or
        # when the editor opened the buffer if they never matched (None for a file that
        # didn't exist). See `sync`.
        self.in_sync: dict[str, str] = {}
        self.disk_baseline: dict[str, str | None] = {}
        self.bridge: asyncio.Server | None = None

    def forget(self, uri: str) -> None:
        """Drop what we remember about a document the editor opened afresh or closed."""
        for remembered in (self.sent_keys, self.in_sync, self.disk_baseline):
            remembered.pop(key(uri), None)


def key(uri: str) -> str:
    return unquote(uri)


def managed(ls: CommentsServer, uri: str) -> TextDocument | None:
    """The open document `uri` names, or None. (`workspace.get_text_document` would make
    one from the file instead.)"""
    return ls.workspace.text_documents.get(key(uri))


def open_by_uri(ls: CommentsServer, uri: str) -> TextDocument:
    document = managed(ls, uri)
    if document is None:
        raise Refused(f"{uri} is not an open document")
    return document


def open_by_path(ls: CommentsServer, path: Path) -> TextDocument | None:
    """The open document at `path`, comparing resolved paths. Each document's path comes
    from the uri the editor sent, decoded once."""
    target = path.resolve()
    for document in ls.workspace.text_documents.values():
        if document.path and Path(document.path).resolve() == target:
            return document
    return None


def kind(document: TextDocument) -> model.FileKind | None:
    return model.file_kind(str(Path(document.path).resolve())) if document.path else None


def codec(ls: CommentsServer, text: str) -> positions.Codec:
    agreed = ls.workspace.position_encoding
    encoding = getattr(agreed, "value", agreed) or "utf-16"
    return positions.Codec(text, ty.cast(positions.Encoding, encoding))
