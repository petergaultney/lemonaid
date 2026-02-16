"""Channel ID construction for lemonaid notifications."""


def channel_id(backend: str, session_id: str) -> str:
    """Build a channel identifier from a backend name and session ID.

    Returns e.g. ``"claude:a1b2c3d4"`` or ``"claude:unknown"`` when
    session_id is empty.
    """
    prefix = session_id[:8] if session_id else "unknown"
    return f"{backend}:{prefix}"
