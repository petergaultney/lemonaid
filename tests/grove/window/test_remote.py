"""The grove window showing another machine's web grove: the grove's calls reach that server,
and a lemon opens in the browser."""

import http.server
import threading

import pytest

pytest.importorskip("webview")
pytest.importorskip("PyObjCTools")  # the window needs macOS

from lemonaid.config import load_config  # noqa: E402
from lemonaid.grove.web import changes, server  # noqa: E402
from lemonaid.grove.window import api, remote  # noqa: E402


class _Calls:
    def data(self):
        return {"blocks": ["far"]}

    def search(self, text):
        return [text]

    def jump(self, channel):
        return {"lemon": channel} if channel == "known" else f"No live lemon on {channel}"


@pytest.fixture
def far():
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), server._handler(_Calls(), {}, changes.Changes())
    )
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()
    httpd.server_close()


def _api(base: str, shown: list[str]) -> remote.RemoteApi:
    local = api.Api(
        api.Shared(load_config()),
        hide=lambda: None,
        refresh=lambda: None,
        leave=lambda: None,
        stick=lambda: None,
        drag=lambda: None,
    )
    return remote.RemoteApi(base, local, show=shown.append, home=lambda: shown.append("home"))


def test_the_groves_calls_go_to_the_server(far):
    calls = _api(far, [])

    assert calls.data() == {"blocks": ["far"]}
    assert calls.search("barn") == ["barn"]


def test_a_lemon_shows_its_page_from_the_server_in_the_window_and_comes_back(far):
    shown: list[str] = []
    calls = _api(far, shown)

    assert calls.jump("known") == ""
    assert calls.jump("gone") == "No live lemon on gone"
    calls.home()
    assert shown == [f"{far}lemon?channel=known", "home"]


def test_a_server_that_is_away_shows_as_a_problem_not_an_error():
    calls = _api("http://127.0.0.1:9/", [])

    assert calls.data() is None
    assert "didn't answer" in calls.plant("1", "t", 0, 0)
