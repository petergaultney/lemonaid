import dataclasses
import json
import subprocess

import pytest

from lemonaid.slack import session

from .shared import COOKIE, SESSION, TOKEN, Keychain


@pytest.fixture
def keychain(monkeypatch):
    fake = Keychain()
    monkeypatch.setattr(session, "_run", fake)
    return fake


def test_a_saved_session_loads_back_and_its_secrets_never_reach_an_argument(keychain):
    assert session.load() is None

    session.save(SESSION)

    assert session.load() == SESSION
    assert not any(TOKEN in word or COOKIE in word for args in keychain.argv for word in args)
    assert TOKEN not in repr(SESSION) and COOKIE not in repr(SESSION)


def test_delete_says_whether_there_was_a_session(keychain):
    session.save(SESSION)

    assert session.delete()
    assert session.load() is None
    assert not session.delete()


def test_a_session_too_long_for_one_security_command_is_refused(keychain):
    with pytest.raises(session.KeychainError):
        session.save(dataclasses.replace(SESSION, cookie="x" * 3000))

    assert keychain.items == {}


def _failing(returncode: int, stderr: str):
    def run(args, stdin=""):
        return subprocess.CompletedProcess(args, returncode, "", stderr)

    return run


def test_a_locked_keychain_is_named_with_its_fix(monkeypatch):
    monkeypatch.setattr(session, "_run", _failing(36, "User interaction is not allowed."))

    with pytest.raises(session.KeychainError, match="unlock-keychain"):
        session.save(SESSION)


def test_another_failure_reports_its_status_and_stderr_without_the_secret(monkeypatch):
    value = json.dumps(dataclasses.asdict(SESSION)).encode().hex()
    monkeypatch.setattr(session, "_run", _failing(1, f"boom\nbad value {value}"))

    with pytest.raises(session.KeychainError) as caught:
        session.save(SESSION)

    assert "exited 1" in str(caught.value) and "bad value" in str(caught.value)
    assert value not in str(caught.value) and TOKEN not in str(caught.value)


def test_the_interactive_status_trailer_is_not_the_reported_cause(monkeypatch):
    stderr = (
        "security: SecKeychainItemCreateFromContent (<default>): The specified keychain "
        "could not be found.\nadd-generic-password: returned -25294\n"
    )
    monkeypatch.setattr(session, "_run", _failing(1, stderr))

    with pytest.raises(session.KeychainError, match="could not be found"):
        session.save(SESSION)
