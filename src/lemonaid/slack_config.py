"""The `[slack]` table: how lemonaid signs in to Slack and follows the threads lemons watch."""

import sys
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class SlackConfig:
    workspace: str = ""  # the URL `lemonaid slack signin` opens, such as https://acme.slack.com/
    push: bool = True  # hold the web client's socket, so a reply wakes its followers at once
    fetch_every: float = 60.0  # seconds between fetches of each thread while no socket is up
    presence_every: float = 300.0  # seconds between presence readings while it is up; 0: none


def _workspace(raw: object) -> str:
    url = urllib.parse.urlparse(raw) if isinstance(raw, str) else None
    if raw == "" or (url and url.scheme == "https" and url.hostname):
        return str(raw)

    print("Warning: [slack] workspace must be an https:// URL", file=sys.stderr)
    return SlackConfig.workspace


def _seconds(key: str, raw: object, default: float, least: float) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw < least:
        print(
            f"Warning: [slack] {key} must be a number of seconds, {least:g} or more",
            file=sys.stderr,
        )
        return default

    return float(raw)


def parse(data: dict) -> SlackConfig:
    push = data.get("push", SlackConfig.push)
    if not isinstance(push, bool):
        print("Warning: [slack] push must be true or false", file=sys.stderr)
        push = SlackConfig.push
    return SlackConfig(
        workspace=_workspace(data.get("workspace", SlackConfig.workspace)),
        push=push,
        fetch_every=_seconds(
            "fetch_every",
            data.get("fetch_every", SlackConfig.fetch_every),
            SlackConfig.fetch_every,
            10,
        ),
        presence_every=_seconds(
            "presence_every",
            data.get("presence_every", SlackConfig.presence_every),
            SlackConfig.presence_every,
            0,
        ),
    )
