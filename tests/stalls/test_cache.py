from lemonaid.stalls import cache

from .shared import KEY, snap


def test_a_key_is_handed_out_once_until_stored_and_again_after_the_ttl() -> None:
    c = cache.Cache()
    assert c.due([KEY, KEY], 0) == [KEY]
    assert c.due([KEY], 1) == []
    c.store(KEY, snap(), 2)
    assert c.due([KEY], 100) == []
    assert c.due([KEY], 400) == [KEY]


def test_a_failed_fetch_keeps_the_last_snapshot() -> None:
    c = cache.Cache()
    good = snap()
    c.store(KEY, good, 0)
    c.store(KEY, None, 400)
    assert c.snapshots() == {KEY: good}
