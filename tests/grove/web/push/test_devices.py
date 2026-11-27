"""The devices kept beside the inbox, and the server's signing key."""

import stat

import pytest

from lemonaid.grove.web.push import devices
from tests.grove.web.push import shared

SUB = shared.subscription()


@pytest.fixture(autouse=True)
def _inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "lemonaid.db"))


def test_a_device_is_kept_once_by_its_endpoint(tmp_path):
    devices.add(SUB)
    again = shared.subscription()
    devices.add(again)

    (found,) = devices.all_devices()
    assert (found.endpoint, found.p256dh) == ("https://push.example/ada", again["keys"]["p256dh"])
    assert (tmp_path / "push" / "devices.json").exists()


def test_a_removed_device_is_gone():
    devices.add(SUB)

    assert devices.remove(SUB["endpoint"])
    assert devices.find(SUB["endpoint"]) is None
    assert not devices.remove(SUB["endpoint"])


def test_something_that_isnt_a_subscription_is_refused():
    with pytest.raises(ValueError):
        devices.add({"endpoint": "https://push.example/ada"})
    with pytest.raises(ValueError):
        devices.add({**SUB, "endpoint": "http://push.example/ada"})
    with pytest.raises(ValueError):
        devices.add({**SUB, "keys": {"p256dh": "pub", "auth": "sec"}})
    with pytest.raises(ValueError):
        devices.add({**SUB, "keys": {**SUB["keys"], "auth": "c2Vj"}})


def test_the_key_is_made_once_and_only_its_owner_reads_it(tmp_path):
    first = devices.key()

    assert devices.key() == first
    assert stat.S_IMODE((tmp_path / "push" / "vapid.pem").stat().st_mode) == 0o600
