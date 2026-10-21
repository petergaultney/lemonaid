"""Who answers for a brief: its `responsible-parties`, the people who asked for the work."""

import getpass
import os
import pwd

from ..config import load_config


def default() -> tuple[str, ...]:
    """`[brief] responsible_parties`, else this account's full name, else its login."""
    if configured := load_config().brief.responsible_parties:
        return configured

    try:
        full_name = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except KeyError:
        full_name = ""
    return (full_name or getpass.getuser(),)
