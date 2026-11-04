"""A token a launcher puts in a new lemon's environment, which its hooks record.

A brief waiting on the token goes to the lemon whose inbox row carries it,
whatever terminal that lemon runs in.
"""

import os
import secrets

ENV = "LEMONAID_LAUNCH_TOKEN"
METADATA_KEY = "launch_token"


def new() -> str:
    return secrets.token_hex(8)


def metadata() -> dict[str, str]:
    """The calling lemon's token as inbox row metadata; {} when it was started without one."""
    token = os.environ.get(ENV, "")
    return {METADATA_KEY: token} if token else {}
