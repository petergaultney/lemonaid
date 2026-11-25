"""The grove window's page, served over HTTP: its calls reach the window's `Api`, and a chat
lemon's jump opens its room in the browser."""

import http.server
import json
import threading
import urllib.error
import urllib.request

import pytest

from lemonaid.front_end import chat
from lemonaid.grove.web import server
from lemonaid.inbox import db

ROOM_KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"


class _Calls:
    def data(self):
        return {"blocks": []}

    def search(self, text):
        return [text]


@pytest.fixture
def served():
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), server._handler(_Calls(), b"<html>page</html>")
    )
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, args: list, headers: dict[str, str] | None = None) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(args).encode(),
        method="POST",
        headers={"Content-Type": "application/json"} if headers is None else headers,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None


def test_the_page_is_served_at_the_root(served):
    with urllib.request.urlopen(served + "/") as response:
        assert response.read() == b"<html>page</html>"


def test_api_calls_reach_the_window_api(served):
    assert _post(served + "/api/data", []) == (200, {"blocks": []})
    assert _post(served + "/api/search", ["barn"]) == (200, ["barn"])


def test_a_call_from_the_pages_own_origin_is_answered(served):
    origin = {"Content-Type": "application/json", "Origin": served}

    assert _post(served + "/api/data", [], origin) == (200, {"blocks": []})


def test_a_call_from_another_site_is_refused(served):
    foreign = {"Content-Type": "application/json", "Origin": "http://unrelated.example"}

    assert _post(served + "/api/data", [], foreign)[0] == 403


def test_a_form_style_post_is_refused(served):
    assert _post(served + "/api/data", [], {"Content-Type": "text/plain"})[0] == 403


def test_only_the_window_apis_calls_are_served(served):
    assert _post(served + "/api/__init__", [])[0] == 404
    assert _post(served + "/api/nothing", [])[0] == 404


def test_the_page_gets_the_shim_before_its_own_scripts():
    page = server.html()

    assert page.index("window.pywebview = {api") < page.index("window.groveData = async")


def test_a_chat_lemons_jump_opens_its_room():
    with db.connect() as conn:
        db.register_working(
            conn,
            f"openclaw:{ROOM_KEY}",
            "",
            name="garden",
            metadata={"session_key": ROOM_KEY},
            switch_source=chat.NAME,
        )

    assert server._jump(f"openclaw:{ROOM_KEY}") == {
        "open": "https://matrix.to/#/!g4rd3n:grove.example"
    }


def test_a_terminal_lemon_cant_be_jumped_to_from_a_browser():
    with db.connect() as conn:
        db.register_working(conn, "claude:abc", "", name="worker", switch_source="tmux")

    assert "runs in a terminal" in server._jump("claude:abc")
    assert server._jump("claude:missing") == "No live lemon on claude:missing"
