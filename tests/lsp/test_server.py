"""`lemonaid lsp` driven over stdio by a stand-in editor, as nvim would drive it."""

import asyncio
import os
import sys
import tempfile
import typing as ty
from pathlib import Path

import pytest
from lsprotocol import types
from pygls import uris
from pygls.lsp.client import LanguageClient

from lemonaid.comments import cli, operations, parse
from lemonaid.lsp import positions, registry

_WAIT: ty.Final = 10.0
_CODE: ty.Final = "def f():\n    return 1\n"


class _Editor:
    """Holds each open document's text, applies the server's edits to it the way nvim
    does, and tells the server about each change. With `skip_edits`, it reports the next
    edits as applied without applying them, as nvim does for an edit whose version is
    older than its buffer."""

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.client = LanguageClient("stand-in", "v1")
        self.texts: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        self.edits_received = 0
        self.skip_edits = 0
        self.close_on_edit = False
        self.on_skip: ty.Callable[[], None] = lambda: None
        self.threads: list[dict[str, ty.Any]] = []
        self.diagnostics: list[types.PublishDiagnosticsParams] = []
        self.shown: list[types.ShowDocumentParams] = []
        self.messages: list[str] = []
        self.notified = asyncio.Event()

        @self.client.feature("lemonaid/threads")
        def threads(params: ty.Any) -> None:
            self.threads.append(_plain(params))
            self.notified.set()

        @self.client.feature(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
        def diagnostics(params: types.PublishDiagnosticsParams) -> None:
            self.diagnostics.append(params)

        @self.client.feature(types.WORKSPACE_APPLY_EDIT)
        def apply_edit(params: types.ApplyWorkspaceEditParams) -> types.ApplyWorkspaceEditResult:
            self.edits_received += 1
            if self.close_on_edit:
                for change in params.edit.document_changes or []:
                    assert isinstance(change, types.TextDocumentEdit)
                    self.close(change.text_document.uri)
                return types.ApplyWorkspaceEditResult(applied=False)
            if self.skip_edits:
                self.skip_edits -= 1
                self.on_skip()
                return types.ApplyWorkspaceEditResult(applied=True)
            for change in params.edit.document_changes or []:
                assert isinstance(change, types.TextDocumentEdit)
                self._apply(change)
            return types.ApplyWorkspaceEditResult(applied=True)

        @self.client.feature(types.WINDOW_SHOW_DOCUMENT)
        def show_document(params: types.ShowDocumentParams) -> types.ShowDocumentResult:
            self.shown.append(params)
            return types.ShowDocumentResult(success=True)

        @self.client.feature(types.WINDOW_SHOW_MESSAGE)
        def show_message(params: types.ShowMessageParams) -> None:
            self.messages.append(params.message)

    def _apply(self, change: types.TextDocumentEdit) -> None:
        uri = change.text_document.uri
        text = self.texts[uri]
        codec = positions.Codec(text)
        replaced = sorted(
            (
                codec.offset(positions.Position(e.range.start.line, e.range.start.character)),
                codec.offset(positions.Position(e.range.end.line, e.range.end.character)),
                e.new_text,
            )
            for e in change.edits
            if isinstance(e, types.TextEdit)
        )
        for start, end, new_text in reversed(replaced):
            text = text[:start] + new_text + text[end:]
        self.change(uri, text)

    async def start(self, root: Path) -> None:
        await self.client.start_io(sys.executable, "-m", "lemonaid", "lsp", env=self.env)
        await self.client.initialize_async(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=uris.from_fs_path(str(root)),
                workspace_folders=[
                    types.WorkspaceFolder(uri=uris.from_fs_path(str(root)) or "", name="root")
                ],
            )
        )
        self.client.initialized(types.InitializedParams())
        await _until(lambda: any((Path(self.env["LEMONAID_STATE_DIR"]) / "lsp").glob("*.json")))

    async def stop(self) -> None:
        await self.client.shutdown_async(None)
        self.client.exit(None)
        await self.client.stop()

    def open(self, path: Path, text: str | None = None) -> str:
        uri = uris.from_fs_path(str(path)) or ""
        self.texts[uri] = path.read_text() if text is None else text
        self.versions[uri] = 1
        self.client.text_document_did_open(
            types.DidOpenTextDocumentParams(
                text_document=types.TextDocumentItem(
                    uri=uri, language_id="python", version=1, text=self.texts[uri]
                )
            )
        )
        return uri

    def change(self, uri: str, text: str) -> None:
        self.texts[uri] = text
        self.versions[uri] += 1
        self.client.text_document_did_change(
            types.DidChangeTextDocumentParams(
                text_document=types.VersionedTextDocumentIdentifier(
                    uri=uri, version=self.versions[uri]
                ),
                content_changes=[types.TextDocumentContentChangeWholeDocument(text=text)],
            )
        )

    def save(self, uri: str) -> None:
        Path(uris.to_fs_path(uri) or "").write_text(self.texts[uri])
        self.client.text_document_did_save(
            types.DidSaveTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=uri))
        )

    def reload(self, uri: str) -> None:
        """What an editor does with an unchanged buffer when its file changes on disk."""
        self.change(uri, Path(uris.to_fs_path(uri) or "").read_text())

    def close(self, uri: str) -> None:
        self.client.text_document_did_close(
            types.DidCloseTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=uri))
        )

    async def command(self, name: str, argument: dict[str, ty.Any]) -> ty.Any:
        return await self.client.workspace_execute_command_async(
            types.ExecuteCommandParams(command=name, arguments=[argument])
        )

    async def lemonaid(self, *argv: str) -> tuple[int, str, str]:
        """Run a lemonaid command as a lemon would, while this editor keeps answering."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "lemonaid",
            *argv,
            env=self.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(process.communicate(), _WAIT)
        return ty.cast(int, process.returncode), out.decode(), err.decode()


def _plain(params: ty.Any) -> dict[str, ty.Any]:
    """A custom notification's params arrive as a namespace object; we compare dicts."""
    if isinstance(params, list):
        return [_plain(p) for p in params]  # type: ignore[return-value]
    if hasattr(params, "__dict__") or hasattr(params, "_asdict"):
        items = params._asdict() if hasattr(params, "_asdict") else vars(params)
        return {k: _plain(v) for k, v in items.items()}
    return params


async def _until(condition: ty.Callable[[], bool]) -> None:
    deadline = asyncio.get_running_loop().time() + _WAIT
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.02)


@pytest.fixture
def env(tmp_path) -> ty.Iterator[dict[str, str]]:
    """The server's state directory is short, since a socket's path must be."""
    with tempfile.TemporaryDirectory(prefix="lma-lsp-", dir="/tmp") as state:
        config = tmp_path / "config.toml"
        config.write_text('[comments]\nauthor = "Caleb Gregory"\n')
        environ = {**os.environ, "LEMONAID_STATE_DIR": state, "LEMONAID_CONFIG": str(config)}
        environ.pop("TMUX", None)
        yield environ


def _drive(env: dict[str, str], root: Path, scenario: ty.Callable[[_Editor], ty.Awaitable[None]]):
    async def main() -> None:
        editor = _Editor(env)
        await editor.start(root)
        try:
            await scenario(editor)
        finally:
            await editor.stop()

    asyncio.run(main())


def test_opening_a_document_sends_its_threads_and_a_hint_at_each_anchor(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(
        "# [lma:SleepRib]\n"
        "x = 1\n"
        "\n"
        "# [lma:threads]\n"
        '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}\n'
        '# {"id": "TinOwl", "re": "SleepRib", "author": "BraveFig (Author)", "at": "2026-11-19T19:41:00Z", "body": "because"}\n'
    )

    async def scenario(editor: _Editor) -> None:
        editor.open(code)
        await _until(lambda: bool(editor.threads) and bool(editor.diagnostics))

        [threads] = editor.threads
        assert threads["version"] == 1
        assert [
            (c["id"], c["depth"], c["author"]) for t in threads["threads"] for c in t["comments"]
        ] == [("SleepRib", 0, "Caleb Gregory"), ("TinOwl", 1, "BraveFig (Author)")]
        assert threads["threads"][0]["anchor"]["start"] == {"line": 1, "character": 0}
        [hint] = editor.diagnostics[-1].diagnostics
        assert hint.message == "Caleb Gregory: why? (1 reply)"
        assert hint.severity == types.DiagnosticSeverity.Hint

    _drive(env, tmp_path, scenario)


def test_threads_are_sent_again_only_when_comments_change(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        await _until(lambda: len(editor.threads) == 1)

        editor.change(uri, "# a line above\n" + _CODE)
        await _until(lambda: len(editor.diagnostics) >= 2)
        threads_before_the_comment = len(editor.threads)
        reply = await editor.command(
            "lemonaid.comment",
            {
                "uri": uri,
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 0}},
                "body": "rename f",
            },
        )
        await _until(lambda: len(editor.threads) == 2)

        assert threads_before_the_comment == 1
        assert reply["id"] in editor.texts[uri]
        assert editor.threads[-1]["threads"][0]["comments"][0]["author"] == "Caleb Gregory"

    _drive(env, tmp_path, scenario)


def test_the_editor_commands_reply_and_resolve_in_your_name(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(
        "# [lma:SleepRib]\n"
        "x = 1\n"
        "\n"
        "# [lma:threads]\n"
        '# {"id": "SleepRib", "author": "BraveFig (Author)", "at": "2026-11-19T19:40:00Z", "body": "a draft comment"}\n'
    )

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        answer = await editor.command(
            "lemonaid.reply", {"uri": uri, "re": "SleepRib", "span": [2, 7], "body": "ok"}
        )
        await editor.command("lemonaid.resolve", {"uri": uri, "id": "SleepRib"})

        doc = parse.parse(editor.texts[uri], "python")
        reply = doc.comment(answer["id"])
        assert reply is not None
        assert (reply.re, reply.span, reply.author) == ("SleepRib", (2, 7), "Caleb Gregory")
        assert [(r.resolves, r.author) for r in doc.resolutions] == [("SleepRib", "Caleb Gregory")]

    _drive(env, tmp_path, scenario)


def test_a_lemon_reply_goes_into_a_buffer_with_unsaved_changes(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)
    unsaved = "# typed, not saved\n" + _CODE

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code, unsaved)
        status, out, err = await editor.lemonaid(
            "comments", "add", str(code), "--lines", "2", "--as", "BraveFig (Author)", "a note"
        )
        assert (status, err) == (0, "")
        comment_id = out.strip()

        status, listed, _ = await editor.lemonaid("comments", "list", str(code))

        assert status == 0
        assert code.read_text() == _CODE
        assert editor.texts[uri].startswith("# typed, not saved\n")
        assert parse.parse(editor.texts[uri], "python").comment(comment_id) is not None
        assert "a note" in listed

    _drive(env, tmp_path, scenario)


def test_a_lemon_reply_to_a_saved_buffer_writes_the_file(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        editor.open(code)
        status, out, _ = await editor.lemonaid(
            "comments", "add", str(code), "--lines", "2", "--as", "BraveFig (Author)", "a note"
        )

        assert status == 0
        assert editor.edits_received == 0
        assert out.strip() in code.read_text()

    _drive(env, tmp_path, scenario)


def test_an_edit_the_editor_skips_is_sent_again_once(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(
        "# [lma:SleepRib]\n"
        "x = 1\n"
        "\n"
        "# [lma:threads]\n"
        '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}\n'
    )

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code, "# unsaved\n" + code.read_text())
        editor.skip_edits = 1
        status, out, err = await editor.lemonaid(
            "comments", "reply", str(code), "--re", "SleepRib", "--as", "BraveFig (Author)", "hi"
        )

        assert (status, err) == (0, "")
        assert editor.edits_received == 2
        doc = parse.parse(editor.texts[uri], "python")
        assert [c.id for c in doc.comments] == ["SleepRib", out.strip()]

    _drive(env, tmp_path, scenario)


def test_an_add_the_editor_skips_is_refused(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code, "# unsaved\n" + _CODE)
        editor.skip_edits = 1
        status, _, err = await editor.lemonaid(
            "comments", "add", str(code), "--lines", "2", "--as", "BraveFig (Author)", "a note"
        )

        assert status == 2
        assert "check them and try again" in err
        assert "[lma:" not in editor.texts[uri]

    _drive(env, tmp_path, scenario)


def test_editor_open_shows_the_file_at_a_line(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        status, _, err = await editor.lemonaid("editor", "open", str(code), "--line", "2")
        assert (status, err) == (0, "")
        await editor.lemonaid("editor", "notify", "review guide ready")

        [shown] = editor.shown
        assert shown.uri == uris.from_fs_path(str(code.resolve()))
        assert shown.selection is not None and shown.selection.start.line == 1
        assert not shown.take_focus
        assert editor.messages == ["review guide ready"]

    _drive(env, tmp_path, scenario)


def test_editor_open_refuses_a_file_outside_every_workspace(env, tmp_path) -> None:
    async def scenario(editor: _Editor) -> None:
        status, _, err = await editor.lemonaid("editor", "open", "/etc/hosts")

        assert status == 1
        assert "no editor server has a workspace that holds" in err

    _drive(env, tmp_path, scenario)


def test_the_server_removes_its_record_when_it_shuts_down(env, tmp_path) -> None:
    async def main() -> None:
        editor = _Editor(env)
        await editor.start(tmp_path)
        await editor.stop()

    asyncio.run(main())

    assert list((Path(env["LEMONAID_STATE_DIR"]) / "lsp").iterdir()) == []


def _add(path: Path, line: str, body: str = "a note") -> tuple[str, ...]:
    return ("comments", "add", str(path), "--lines", line, "--as", "BraveFig (Author)", body)


def test_writes_before_the_editor_reloads_all_go_to_the_file(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        first = await editor.lemonaid(*_add(code, "1"))
        second = await editor.lemonaid(*_add(code, "2"))
        editor.reload(uri)
        await _until(lambda: "lma:" in editor.texts[uri])
        third = await editor.lemonaid(*_add(code, "2", "after the reload"))

        assert [status for status, _, _ in (first, second, third)] == [0, 0, 0]
        assert editor.edits_received == 0
        on_disk = parse.parse(code.read_text(), "python")
        assert all(on_disk.comment(out.strip()) for _, out, _ in (first, second, third))

    _drive(env, tmp_path, scenario)


def test_after_you_save_a_lemon_writes_the_file_again(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        editor.change(uri, "# typed\n" + _CODE)
        await editor.lemonaid(*_add(code, "2"))
        editor.save(uri)
        await asyncio.sleep(0.2)
        _, out, _ = await editor.lemonaid(*_add(code, "3", "on disk"))

        assert editor.edits_received == 1
        assert parse.parse(code.read_text(), "python").comment(out.strip()) is not None

    _drive(env, tmp_path, scenario)


def test_an_add_computed_from_a_buffer_that_has_since_changed_is_refused(
    env, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LEMONAID_STATE_DIR", env["LEMONAID_STATE_DIR"])
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code, "# unsaved\n" + _CODE)
        await _until(lambda: bool(editor.diagnostics))
        [server] = registry.live()
        answer = await asyncio.to_thread(
            registry.request,
            server,
            {
                "op": "apply",
                "path": str(code),
                "operation": operations.to_json(operations.Add("1", "BraveFig (Author)", "x")),
                "observed": registry.text_digest("an older buffer"),
            },
        )

        assert "check them and try again" in answer["error"]
        assert "[lma:" not in editor.texts[uri]

    _drive(env, tmp_path, scenario)


@pytest.mark.parametrize("name", ["review notes.md", "review%20notes.md"])
def test_a_file_whose_name_needs_escaping_is_still_found(env, tmp_path, name) -> None:
    notes = tmp_path / name
    notes.write_text("# Notes\n\nsome text\n")

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(notes, "# Notes\n\nsome text, unsaved\n")
        answer = await editor.command(
            "lemonaid.comment",
            {
                "uri": uri,
                "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 4}},
                "body": "from the editor",
            },
        )
        status, out, err = await editor.lemonaid(*_add(notes, "1", "from a lemon"))

        assert (status, err) == (0, "")
        assert answer["id"] in editor.texts[uri]
        assert out.strip() in editor.texts[uri]
        assert "lma:" not in notes.read_text()

    _drive(env, tmp_path, scenario)


def test_a_reply_stops_when_the_editor_closes_the_file(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(
        "# [lma:SleepRib]\n"
        "x = 1\n"
        "\n"
        "# [lma:threads]\n"
        '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}\n'
    )
    on_disk = code.read_text()

    async def scenario(editor: _Editor) -> None:
        editor.open(code, "# unsaved\n" + on_disk)
        editor.close_on_edit = True
        status, _, err = await editor.lemonaid(
            "comments", "reply", str(code), "--re", "SleepRib", "--as", "BraveFig (Author)", "hi"
        )

        assert status == 2
        assert "closed the file" in err
        assert editor.edits_received == 1
        assert code.read_text() == on_disk

    _drive(env, tmp_path, scenario)


def test_a_long_comment_reaches_an_unsaved_buffer(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)
    body = "x" * 66_000

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code, "# unsaved\n" + _CODE)
        status, out, err = await editor.lemonaid(*_add(code, "2", body))

        assert (status, err) == (0, "")
        comment = parse.parse(editor.texts[uri], "python").comment(out.strip())
        assert comment is not None and comment.body == body

    _drive(env, tmp_path, scenario)


def test_a_write_is_refused_while_buffer_and_file_have_both_changed(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        first = await editor.lemonaid(*_add(code, "1"))
        editor.change(uri, "# typed before the reload\n" + _CODE)
        await _until(lambda: len(editor.diagnostics) >= 2)
        status, _, err = await editor.lemonaid(*_add(code, "2"))

        assert first[0] == 0
        assert status == 2
        assert "save or reload" in err
        assert "lma:" not in editor.texts[uri]
        assert parse.parse(code.read_text(), "python").comment(first[1].strip()) is not None
        assert editor.edits_received == 0

    _drive(env, tmp_path, scenario)


def test_an_add_whose_unsaved_buffer_was_reverted_is_refused(env, tmp_path, monkeypatch) -> None:
    """The CLI saw unsaved changes, then the buffer went back to the file's text before
    the server wrote: the same line numbers in the file name other text."""
    monkeypatch.setenv("LEMONAID_STATE_DIR", env["LEMONAID_STATE_DIR"])
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        editor.open(code)
        await _until(lambda: bool(editor.diagnostics))
        [server] = registry.live()
        seen = [cli._Buffer(server, "# unsaved\n" + _CODE, "unsaved")]
        monkeypatch.setattr(cli, "_open_buffers", lambda _: seen)

        with pytest.raises(cli._Refused, match="line numbers may name other code"):
            await asyncio.to_thread(
                cli._carry_out, code, operations.Add("1", "BraveFig (Author)", "x"), retry=False
            )

        assert code.read_text() == _CODE

    _drive(env, tmp_path, scenario)


def test_an_editor_comment_is_refused_while_buffer_and_file_have_both_changed(
    env, tmp_path
) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        await editor.lemonaid(*_add(code, "1"))
        editor.change(uri, "# typed before the reload\n" + _CODE)
        await _until(lambda: len(editor.diagnostics) >= 2)

        with pytest.raises(Exception, match="save or reload"):
            await editor.command(
                "lemonaid.comment",
                {
                    "uri": uri,
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 0},
                    },
                    "body": "stale",
                },
            )

        assert editor.edits_received == 0

    _drive(env, tmp_path, scenario)


def test_a_retry_is_refused_once_the_file_changes_under_an_unsaved_buffer(env, tmp_path) -> None:
    code = tmp_path / "code.py"
    code.write_text(
        "# [lma:SleepRib]\n"
        "x = 1\n"
        "\n"
        "# [lma:threads]\n"
        '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}\n'
    )

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        editor.change(uri, "# unsaved\n" + code.read_text())
        await _until(lambda: len(editor.diagnostics) >= 2)
        editor.skip_edits = 1
        editor.on_skip = lambda: code.write_text(code.read_text() + "# changed on disk\n")
        status, _, err = await editor.lemonaid(
            "comments", "reply", str(code), "--re", "SleepRib", "--as", "BraveFig (Author)", "hi"
        )

        assert status == 2
        assert "save or reload" in err
        assert editor.edits_received == 1

    _drive(env, tmp_path, scenario)


def test_an_editor_comment_waits_for_the_reload_after_a_lemon_writes_the_file(
    env, tmp_path
) -> None:
    code = tmp_path / "code.py"
    code.write_text(_CODE)

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(code)
        await editor.lemonaid(*_add(code, "1"))
        await _until(lambda: bool(editor.diagnostics))

        with pytest.raises(Exception, match="save or reload"):
            await editor.command(
                "lemonaid.comment",
                {
                    "uri": uri,
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 0},
                    },
                    "body": "before the reload",
                },
            )
        editor.reload(uri)
        await _until(lambda: "lma:" in editor.texts[uri])
        answer = await editor.command(
            "lemonaid.comment",
            {
                "uri": uri,
                "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 0}},
                "body": "after the reload",
            },
        )

        assert answer["id"] in editor.texts[uri]
        assert editor.edits_received == 1

    _drive(env, tmp_path, scenario)


def test_a_buffer_unsaved_when_it_opens_notices_the_file_changing(env, tmp_path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n\nsaved text\n")

    async def scenario(editor: _Editor) -> None:
        uri = editor.open(notes, "# Notes\n\nunsaved text\n")
        await _until(lambda: bool(editor.diagnostics))
        notes.write_text("# Notes\n\nsaved text, changed elsewhere\n")
        status, _, err = await editor.lemonaid(*_add(notes, "3"))

        assert status == 2
        assert "save or reload" in err
        assert "lma:" not in editor.texts[uri]
        assert "lma:" not in notes.read_text()

    _drive(env, tmp_path, scenario)
