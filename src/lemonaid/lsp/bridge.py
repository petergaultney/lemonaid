"""The unix socket through which a lemon's `lemonaid comments` reads and edits a buffer, and
`lemonaid editor` opens files and shows messages. `registry` describes the protocol."""

import asyncio
import atexit
import json
import logging
import os
import time
import typing as ty
from pathlib import Path

from lsprotocol import types
from pygls import uris

from ..comments import edits, operations
from . import documents, editing, registry, sync
from .documents import CommentsServer, Refused

_LOG: ty.Final = logging.getLogger(__name__)
# The longest request line the socket accepts. A comment's body is in it, so it is well
# past any comment a person or a lemon writes, and it bounds what a stray client can make
# the server hold.
_REQUEST_LIMIT: ty.Final = 64 * 1024 * 1024


async def start(ls: CommentsServer) -> None:
    pid = os.getpid()
    path = registry.socket_path(pid)
    if path is None:
        _LOG.warning("lemonaid's state directory path is too long for a socket")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    ls.bridge = await asyncio.start_unix_server(
        lambda reader, writer: _serve(ls, reader, writer), path=str(path), limit=_REQUEST_LIMIT
    )
    roots = [Path(uris.to_fs_path(folder.uri) or "") for folder in ls.workspace.folders.values()]
    if not roots and ls.workspace.root_path:
        roots = [Path(ls.workspace.root_path)]
    registry.write(
        registry.Record(
            pid=pid,
            socket=str(path),
            roots=tuple(str(root.resolve()) for root in roots if str(root)),
            tmux=registry.tmux_session(),
            started=time.time(),
        )
    )
    atexit.register(registry.remove, pid)


def stop(ls: CommentsServer) -> None:
    if ls.bridge is not None:
        ls.bridge.close()
        ls.bridge = None
    registry.remove(os.getpid())


async def _serve(
    ls: CommentsServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        try:
            line = await reader.readline()
            answer = await _answer(ls, json.loads(line))
        except (Refused, ValueError, KeyError, TypeError) as refusal:
            answer = {"error": str(refusal)}
        except Exception as error:
            _LOG.exception("lemonaid lsp: a request on the socket failed")
            answer = {"error": f"the editor server failed: {error!r}"}
        writer.write(json.dumps(answer).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()


async def _answer(ls: CommentsServer, message: dict[str, ty.Any]) -> dict[str, ty.Any]:
    match message["op"]:
        case "buffer":
            document = documents.open_by_path(ls, Path(message["path"]))
            if document is None:
                return {"open": False}
            return {"open": True, "text": document.source, "state": sync.state(ls, document)}
        case "apply":
            document = documents.open_by_path(ls, Path(message["path"]))
            if document is None:
                return {"open": False}
            state = sync.state(ls, document)
            if state == "diverged":
                raise Refused(sync.DIVERGED)
            if state == "clean":
                return {"open": True, "state": state}
            operation = operations.from_json(message["operation"])
            observed = message.get("observed")
            result = await editing.apply(
                ls,
                document,
                editing.operation_change(operation, edits.now()),
                retry=not isinstance(operation, operations.Add),
                observed=observed if isinstance(observed, str) else None,
            )
            return {"open": True, "state": state, "result": result}
        case "show":
            line = message.get("line")
            selection = (
                types.Range(
                    start=types.Position(line=line - 1, character=0),
                    end=types.Position(line=line - 1, character=0),
                )
                if isinstance(line, int) and line >= 1
                else None
            )
            shown = await ls.window_show_document_async(
                types.ShowDocumentParams(
                    uri=uris.from_fs_path(str(Path(message["path"]))) or "",
                    take_focus=bool(message.get("focus")),
                    selection=selection,
                )
            )
            return {"shown": shown.success}
        case "message":
            ls.window_show_message(
                types.ShowMessageParams(type=types.MessageType.Info, message=message["text"])
            )
            return {}
    raise ValueError(f"unknown request {message['op']!r}")
