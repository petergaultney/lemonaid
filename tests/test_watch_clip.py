from lemonaid.watch import clip


def test_each_part_gets_an_equal_share_and_stays_identifiable():
    parts = ["[pr] " + "a" * 40000, "[mailbox] short", "[doc] " + "b" * 40000]

    shared = clip.share(parts, 30000)

    assert [p[:5] for p in shared] == ["[pr] ", "[mail", "[doc]"]
    assert shared[1] == parts[1]
    assert sum(len(p) for p in shared) < 30500
