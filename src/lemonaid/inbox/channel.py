"""Channel ID construction for lemonaid notifications."""


class UnidentifiedSession(Exception):
    """Raised when a notification carries no session to attribute it to."""


def channel_id(backend: str, session_id: str | None) -> str:
    """Build a channel identifier from a backend name and session ID.

    Returns e.g. ``"claude:a1b2c3d4"``.

    Raises `UnidentifiedSession` when there is no session id. A shared
    placeholder channel looks like one more session in the inbox, and it
    inherits the tty of whatever shell delivered it - so it lands on a real
    pane, and the next unidentified notification upserts over it. Every
    backend's payload carries an id in practice; a missing one means a
    malformed call, which is worth dropping rather than filing under a
    pane someone is using.
    """
    if not session_id:
        raise UnidentifiedSession(f"{backend} notification has no session id")

    return f"{backend}:{session_id[:8]}"
