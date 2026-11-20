"""A Codex lemon's inbox channel is `codex:` and its whole thread ID."""


def channel(thread: str) -> str:
    return f"codex:{thread}"


def thread(channel: str) -> str:
    return channel.removeprefix("codex:")
