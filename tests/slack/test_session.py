import dataclasses

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
