"""Slack Web API calls as the web client makes them: token in the form, `d` cookie in a header.

Only the read methods in `READ_METHODS` can be called; the session can write anything the
user can, and lemonaid never does. Errors name the method and Slack's error code, never the
token or the cookie.
"""

import json
import typing as ty
import urllib.error
import urllib.parse
import urllib.request

from . import session

READ_METHODS = frozenset(
    {
        "auth.test",
        "conversations.history",
        "conversations.replies",
        "users.info",
        "users.getPresence",
    }
)
# Slack's answers to a session it no longer accepts; anything else is about the one call.
EXPIRED = frozenset(
    {"invalid_auth", "token_revoked", "token_expired", "account_inactive", "not_authed"}
)
_TIMEOUT = 30.0
_open = urllib.request.urlopen  # tests replace it; they never reach Slack


class Expired(Exception):
    """Slack refused the session: the user signs in again."""


class Unavailable(OSError):
    """Slack could not be reached, or asked lemonaid to slow down; try again later."""


class Failed(RuntimeError):
    """Slack answered the call with an error about it, such as a thread that is gone."""


def call(current: session.Session, method: str, **params: str) -> dict[str, ty.Any]:
    if method not in READ_METHODS:
        raise ValueError(f"{method} is not one of the Slack methods lemonaid may call")

    request = urllib.request.Request(
        f"{current.api_url.rstrip('/')}/api/{method}",
        data=urllib.parse.urlencode({"token": current.token, **params}).encode(),
        headers={
            "Cookie": f"d={current.cookie}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with _open(request, timeout=_TIMEOUT) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise Unavailable(f"{method}: HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise Unavailable(f"{method}: {type(error).__name__}") from None

    if body.get("ok"):
        return body

    code = str(body.get("error") or "unknown error")
    if code in EXPIRED:
        raise Expired(f"{method}: {code}")
    if code == "ratelimited":
        raise Unavailable(f"{method}: rate limited")
    raise Failed(f"{method}: {code}")
