"""The grove window's page, served over HTTP: its calls reach the window's `Api`, and a jump
opens the lemon's own page."""

import gzip
import http.client
import http.server
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from lemonaid.brief import pr
from lemonaid.config import BriefConfig, Config, load_config
from lemonaid.front_end import chat
from lemonaid.grove.layout import state
from lemonaid.grove.source import blocks, live
from lemonaid.grove.web import changes, notes, server
from lemonaid.grove.window import api, data
from lemonaid.inbox import db
from tests.grove import shared

ROOM_KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"


class _Calls:
    def data(self):
        return {"blocks": []}

    def search(self, text):
        return [text]

    def switch(self, channel):
        return f"switched to {channel}"

    def keep(self, settings):
        return None

    def block_refusal(self, digit, sides, dx, dy):
        return ""


@pytest.fixture
def seen():
    return changes.Changes()


@pytest.fixture
def served(seen):
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        server._handler(
            _Calls(),
            {
                "grove": (b"<html>page</html>", "text/html"),
                "lemon": (b"<html>lemon</html>", "text/html"),
                "groups": (b"<html>groups</html>", "text/html"),
                "icon.svg": (b"<svg/>", "image/svg+xml"),
            },
            seen,
        ),
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


def test_the_page_comes_compressed_and_a_browser_that_has_it_isnt_sent_it_again(seen):
    big = server._handler(
        _Calls(), {"grove": (b"<html>" + b"lemon " * 1000 + b"</html>", "text/html")}, seen
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), big)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        connection.request("GET", "/", headers={"Accept-Encoding": "gzip"})
        first = connection.getresponse()
        page = gzip.decompress(first.read())
        connection.request("GET", "/", headers={"If-None-Match": first.getheader("ETag")})
        again = connection.getresponse()
        again.read()
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert first.getheader("Content-Encoding") == "gzip" and page.startswith(b"<html>lemon")
    assert again.status == 304


def test_a_phone_is_sent_to_the_groups(served):
    phone = urllib.request.Request(
        served + "/", headers={"User-Agent": "Mozilla/5.0 (Android 17; Mobile)"}
    )
    with urllib.request.urlopen(phone) as response:
        assert (response.url, response.read()) == (served + "/groups", b"<html>groups</html>")

    with urllib.request.urlopen(served + "/grove") as response:
        assert response.read() == b"<html>page</html>"


def test_the_icon_is_served_as_an_image(served):
    with urllib.request.urlopen(served + "/icon.svg") as response:
        assert (response.headers["Content-Type"], response.read()) == ("image/svg+xml", b"<svg/>")


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


def test_only_the_calls_named_for_browsers_are_served(served):
    assert _post(served + "/api/__init__", [])[0] == 404
    assert _post(served + "/api/nothing", [])[0] == 404
    assert _post(served + "/api/open_link", ["https://example.com"])[0] == 404
    assert _post(served + "/api/drag", [])[0] == 404


def test_the_lemon_page_is_served_with_its_query(served):
    with urllib.request.urlopen(served + "/lemon?channel=claude%3Aabc") as response:
        assert response.read() == b"<html>lemon</html>"


def test_a_browser_on_the_server_may_switch_its_terminal(served):
    assert _post(served + "/api/switch", ["claude:abc"]) == (200, "switched to claude:abc")


def test_a_browser_elsewhere_may_not_switch_the_servers_terminal(served, monkeypatch):
    monkeypatch.setattr(server, "_LOOPBACK", frozenset())

    assert _post(served + "/api/switch", ["claude:abc"])[0] == 403


def test_a_jump_opens_the_lemons_page():
    with db.connect() as conn:
        db.register_working(
            conn,
            f"openclaw:{ROOM_KEY}",
            "",
            name="garden",
            metadata={"session_key": ROOM_KEY},
            switch_source=chat.NAME,
        )
    window = dict.fromkeys(("hide", "refresh", "leave", "stick", "drag"), lambda: None)
    calls = server._WebApi(api.Shared(Config()), pr.no_state, **window)

    assert calls.jump(f"openclaw:{ROOM_KEY}") == {"lemon": f"openclaw:{ROOM_KEY}"}
    assert calls.jump("claude:missing") == "No live lemon on claude:missing"
    assert calls.lemon("claude:missing") == {"error": "No live lemon on claude:missing"}


def test_an_open_page_hears_each_change(served, seen):
    with urllib.request.urlopen(served + "/api/changes", timeout=5) as stream:
        assert stream.headers["Content-Type"] == "text/event-stream"
        assert stream.readline() == b"retry: 1000\n"
        seen.saw({"blocks": [1]})
        assert [stream.readline(), stream.readline(), stream.readline()] == [
            b"\n",
            b"data: 1\n",
            b"\n",
        ]


def test_streams_past_a_clients_few_are_turned_away_and_its_calls_still_answer(served):
    streams = [urllib.request.urlopen(served + "/api/changes", timeout=5) for _ in range(3)]
    try:
        assert [stream.status for stream in streams] == [200, 200, 204]
        assert _post(served + "/api/search", ["barn"]) == (200, ["barn"])
    finally:
        for stream in streams:
            stream.close()


def test_each_browser_behind_a_proxy_on_this_machine_gets_its_own_streams(served):
    def stream(browser: str) -> http.client.HTTPResponse:
        request = urllib.request.Request(
            served + "/api/changes", headers={"X-Forwarded-For": browser}
        )
        return urllib.request.urlopen(request, timeout=5)

    streams = [stream(browser) for browser in ("100.64.0.1",) * 3 + ("100.64.0.2",)]
    try:
        assert [each.status for each in streams] == [200, 200, 204, 200]
    finally:
        for each in streams:
            each.close()


def test_a_lemons_page_gets_a_stream_of_its_own_changes(served):
    stream = urllib.request.urlopen(served + "/api/talk-changes?channel=claude%3Agone", timeout=5)
    try:
        assert stream.status == 200
        assert stream.headers.get_content_type() == "text/event-stream"
        assert stream.readline() == b"retry: 1000\n"
    finally:
        stream.close()


def test_a_stream_a_page_closes_frees_its_place(served):
    kept = urllib.request.urlopen(served + "/api/changes", timeout=5)
    urllib.request.urlopen(served + "/api/changes", timeout=5).close()
    time.sleep(2 * changes.CHECK_SECONDS)
    try:
        with urllib.request.urlopen(served + "/api/changes", timeout=5) as again:
            assert again.status == 200
    finally:
        kept.close()


def test_a_pages_calls_share_one_connection_even_after_a_refusal(served):
    connection = http.client.HTTPConnection(served.removeprefix("http://"), timeout=5)
    headers = {"Content-Type": "application/json"}
    answers = []
    for path in ("/api/nothing", "/api/search", "/api/search"):
        connection.request("POST", path, body=json.dumps(["barn"]), headers=headers)
        response = connection.getresponse()
        answers.append((response.status, response.read(), response.will_close))
    connection.close()

    assert answers == [
        (404, b"not found", False),
        (200, b'["barn"]', False),
        (200, b'["barn"]', False),
    ]


def _noted() -> list[dict]:
    found = notes.path()
    return [json.loads(line) for line in found.read_text().splitlines()] if found.exists() else []


def test_a_pages_notes_go_to_the_log(served):
    request = urllib.request.Request(
        served + "/api/note",
        data=json.dumps([{"what": "load", "w": 412, "h": 915, "touch": True}]).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.status == 204

    (noted,) = _noted()
    assert (noted["kind"], noted["what"], noted["w"], noted["client"]) == (
        "page",
        "load",
        412,
        "127.0.0.1",
    )


def test_the_log_keeps_saved_views_and_leaves_out_routine_polls(served):
    _post(served + "/api/data", [])
    _post(served + "/api/block_refusal", ["2", [], 1, 0])
    _post(served + "/api/keep", [{"views": {"412x915": {"grove": {"k": 4.9}}}}])

    assert [(n["call"], n["args"]) for n in _noted()] == [
        ("keep", [{"views": {"412x915": {"grove": {"k": 4.9}}}}])
    ]


def test_a_phones_page_edits_a_lemon_it_knows_only_by_its_channel(monkeypatch):
    with db.connect() as conn:
        for name in ("first", "second", "hidden"):  # the grove shows only the first two
            db.add(conn, f"claude:{name}", "a message", name, {"tty": f"/dev/ttys5{name}"})
    two = shared.tree("s", shared.lemon("claude:first"), shared.lemon("claude:second"))
    monkeypatch.setattr(blocks, "blocks", lambda *_args, **_kw: (shared.block("a", "1", two),))
    state.save(
        {"version": state.VERSION} | shared.stream_saved({"a": shared.plot_data(2, 2, 60, 14)})
    )
    live.fresh(load_config(), None)
    refreshed: list[int] = []
    window = dict.fromkeys(("hide", "leave", "stick", "drag"), lambda: None)
    loading = server._WebApi(api.Shared(Config()), pr.no_state, refresh=lambda: None, **window)
    calls = server._WebApi(
        api.Shared(Config(), grove=data.load(load_config())),
        pr.no_state,
        refresh=lambda: refreshed.append(1),
        **window,
    )

    assert {"lemon_edit", "lemon_edit_info"} <= server._CALLS and "pin" not in server._CALLS
    pinned = {"said": "pinned 1 lemon", "gone": False}
    assert calls.lemon_edit("pin", "claude:second", "") == pinned
    assert calls.lemon_edit("pin", "claude:first", "") == pinned
    assert calls.pins() == ["claude:second", "claude:first"]
    assert calls.lemon_edit_info("snooze", "claude:first")["presets"]
    assert calls.lemon_edit("archive", "claude:first", "") == {
        "said": "archived 1 lemon",
        "gone": True,
    }
    assert calls.lemon_edit("archive", "claude:hidden", "") == {
        "said": "the grove doesn't show that lemon",
        "gone": False,
    }
    assert loading.lemon_edit_info("rename", "claude:first") == {"problem": "the grove is loading"}
    assert refreshed == [1, 1, 1]  # each edit the grove shows


def test_a_page_asks_which_vaults_the_servers_links_open(tmp_path):
    config = Config(brief=BriefConfig(vaults=(tmp_path / "trove", tmp_path / "work")))
    window = dict.fromkeys(("hide", "leave", "stick", "drag", "refresh"), lambda: None)
    calls = server._WebApi(api.Shared(config), pr.no_state, **window)

    assert calls.vaults() == ["trove", "work"]
    assert "vaults" in server._CALLS


def test_a_page_attaches_and_removes_files():
    window = dict.fromkeys(("hide", "leave", "stick", "drag", "refresh"), lambda: None)
    calls = server._WebApi(api.Shared(Config()), pr.no_state, **window)

    saved = calls.attach("a.txt", "text/plain", "aGk=")
    assert isinstance(saved, dict) and saved["size"] == 2
    assert calls.detach(saved["id"]) == ""
    assert {"attach", "detach", "say"} <= server._CALLS


def test_a_call_larger_than_any_attachment_is_refused_unread(served, monkeypatch):
    monkeypatch.setattr(server, "_MAX_CALL_BYTES", 100)

    assert _post(f"{served}/api/search", ["x" * 200])[0] == 413
    assert _post(f"{served}/api/search", ["barn"]) == (200, ["barn"])
