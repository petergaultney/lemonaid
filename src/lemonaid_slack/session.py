"""The user's Slack web session (the web client's token and its `d` cookie), kept only in the
macOS Keychain.

The item is written and read through the `security` tool, so the Keychain trusts `security`
rather than one Python binary, and the scout host reads it without a prompt after an upgrade.
The secret goes to `security` on its stdin, never in its arguments, where `ps` would show it.
Nothing here logs or prints the token or the cookie; `Session`'s repr leaves them out.
"""

import dataclasses
import json
import re
import subprocess

from . import wakes

SERVICE = "lemonaid-slack"
_ACCOUNT = "session"
_NOT_FOUND = 44  # `security`'s exit status for a missing item
_NO_INTERACTION = 36  # the login keychain is locked, or this process has no GUI security session
_STATUS_TRAILER = re.compile(r"[\w-]+: returned -?\d+")
_UNLOCK = "security unlock-keychain ~/Library/Keychains/login.keychain-db"
_LINE_LIMIT = 4000  # `security -i` splits a longer command line, saving part of the value


class KeychainError(OSError):
    pass


@dataclasses.dataclass(frozen=True)
class Session:
    api_url: str  # where Web API calls go, from auth.test, such as https://acme.slack.com/
    user_id: str
    user: str
    team: str
    token: str = dataclasses.field(repr=False)
    cookie: str = dataclasses.field(repr=False)  # `d`, URL-encoded as the cookie store holds it
    cookie_expires: str = ""
    team_id: str = ""
    enterprise_id: str = ""
    captured_at: float = 0.0  # which sign-in this is; a new one replaces an expired session


def _run(args: list[str], stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(["security", *args], input=stdin, capture_output=True, text=True)


def _failure(action: str, done: subprocess.CompletedProcess, secret: str = "") -> KeychainError:
    if done.returncode == _NO_INTERACTION:
        return KeychainError(
            f"can't {action} the {SERVICE} Keychain item: the login keychain is locked, or this "
            f"shell can't reach the macOS GUI session (as in tmux or SSH). Run `{_UNLOCK}`, "
            "or run this from a shell outside tmux"
        )

    lines = [  # `security -i` ends its error with a "<command>: returned <status>" line
        line
        for line in (done.stderr.replace(secret, "") if secret else done.stderr).splitlines()
        if line.strip() and not _STATUS_TRAILER.fullmatch(line.strip())
    ]
    detail = f": {lines[-1]}" if lines else ""
    return KeychainError(
        f"can't {action} the {SERVICE} Keychain item: security exited {done.returncode}{detail}"
    )


def load() -> Session | None:
    found = _run(["find-generic-password", "-s", SERVICE, "-a", _ACCOUNT, "-w"])
    if found.returncode == _NOT_FOUND:
        return None

    if found.returncode:
        raise _failure("read", found)

    raw = found.stdout.strip()
    try:
        return Session(**json.loads(raw if raw.startswith("{") else bytes.fromhex(raw).decode()))
    except (ValueError, TypeError) as error:
        raise KeychainError(f"the {SERVICE} Keychain item is not a lemonaid session") from error


def save(session: Session) -> None:
    value = json.dumps(dataclasses.asdict(session)).encode().hex()
    command = f"add-generic-password -U -s {SERVICE} -a {_ACCOUNT} -l {SERVICE} -X {value}\n"
    if len(command) > _LINE_LIMIT:
        raise KeychainError("the session is too long for the Keychain item")

    saved = _run(["-i"], command)
    wakes.session_changed()
    if saved.returncode:
        raise _failure("save", saved, value)

    if load() != session:
        raise KeychainError(f"the {SERVICE} Keychain item did not keep the session")


def delete() -> bool:
    """Whether there was a session to delete."""
    deleted = _run(["delete-generic-password", "-s", SERVICE, "-a", _ACCOUNT]).returncode == 0
    wakes.session_changed()
    return deleted
