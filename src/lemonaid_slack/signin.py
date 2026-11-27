"""Turn what the sign-in window found into a saved session: the first token the page holds that
`auth.test` accepts with the `d` cookie.
"""

import dataclasses
import time
from collections import abc

from . import api, session, signed_out


def tokens(look: dict) -> list[str]:
    """The web client tokens a look at the page found, best first, without repeats.

    `localConfig_v2` holds one per team the user is signed in to (an enterprise can list
    several); any other localStorage value, and the client's own API calls, are fallbacks.
    """
    found = [
        *(t.get("token", "") for t in look.get("teams") or ()),
        *(h.get("token", "") for h in look.get("stored") or ()),
        look.get("called", ""),
    ]
    return list(dict.fromkeys(t for t in found if t.startswith("xoxc-")))


def capture(
    candidates: abc.Iterable[str],
    cookie: str,
    cookie_expires: str,
    workspace: str,
    rejections: list[str] | None = None,
) -> session.Session | None:
    """The session for the first candidate Slack accepts, or None; each refusal's reason goes on
    *rejections*."""
    for token in candidates:
        probe = session.Session(
            api_url=workspace,
            user_id="",
            user="",
            team="",
            token=token,
            cookie=cookie,
            cookie_expires=cookie_expires,
            captured_at=time.time(),
        )
        try:
            body = api.call(probe, "auth.test")
        except (api.Expired, api.Failed) as error:
            if rejections is not None:
                rejections.append(f"Slack rejected the page's token ({error})")
            continue

        return dataclasses.replace(
            probe,
            api_url=body.get("url") or workspace,
            user_id=body.get("user_id", ""),
            user=body.get("user", ""),
            team=body.get("team", ""),
            team_id=body.get("team_id", ""),
            enterprise_id=body.get("enterprise_id") or "",
        )
    return None


def keep(found: session.Session) -> None:
    session.save(found)
    signed_out.signed_in()
