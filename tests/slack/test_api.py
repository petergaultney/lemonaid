import io
import json
import urllib.error

import pytest

from lemonaid.slack import api

from .shared import COOKIE, SESSION, TOKEN


def _answering(body: dict, sent: list):
    def urlopen(request, timeout):
        sent.append(request)
        return io.BytesIO(json.dumps(body).encode())

    return urlopen


def test_a_call_sends_the_token_in_the_form_and_the_cookie_in_a_header(monkeypatch):
    sent: list = []
    monkeypatch.setattr(api, "_open", _answering({"ok": True, "user": "sam"}, sent))

    assert api.call(SESSION, "auth.test")["user"] == "sam"

    [request] = sent
    assert request.full_url == "https://acme.slack.com/api/auth.test"
    assert f"token={TOKEN}" in request.data.decode()
    assert request.get_header("Cookie") == f"d={COOKIE}"


def test_only_read_methods_are_called(monkeypatch):
    sent: list = []
    monkeypatch.setattr(api, "_open", _answering({"ok": True}, sent))

    with pytest.raises(ValueError, match=r"chat\.postMessage"):
        api.call(SESSION, "chat.postMessage", channel="C1", text="hi")

    assert sent == []


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        ("invalid_auth", api.Expired),
        ("token_revoked", api.Expired),
        ("ratelimited", api.Unavailable),
        ("thread_not_found", api.Failed),
    ],
)
def test_slack_errors_name_the_method_and_code_and_never_a_secret(monkeypatch, error, raised):
    monkeypatch.setattr(api, "_open", _answering({"ok": False, "error": error}, []))

    with pytest.raises(raised) as caught:
        api.call(SESSION, "conversations.replies", channel="C1", ts="1.2")

    assert "conversations.replies" in str(caught.value)
    assert TOKEN not in str(caught.value) and COOKIE not in str(caught.value)


def test_an_unreachable_slack_is_unavailable(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(api, "_open", urlopen)

    with pytest.raises(api.Unavailable):
        api.call(SESSION, "auth.test")
