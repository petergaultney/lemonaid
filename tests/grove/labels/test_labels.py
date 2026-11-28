from lemonaid.grove.layout.labels import labels


def test_drops_path_prefixes_and_the_groups_own_words():
    found = labels("shop-postgres", ["billing/postgres-core", "protostellar/shop-postgres-roles"])
    assert found == {"billing/postgres-core": "core", "protostellar/shop-postgres-roles": "roles"}


def test_drops_words_most_trees_share():
    keys = [
        "billing/data-layout-design",
        "billing/soak-testing-design",
        "billing/limits-design",
        "shop-hq",
    ]
    assert labels("shop", keys)["billing/data-layout-design"] == "data layout"


def test_keeps_words_only_half_the_trees_share():
    keys = ["th/local-move-event", "upstream/local-move-event", "git-sync-wedge", "kms-report"]
    assert labels("relay", keys)["th/local-move-event"] == "local move event"


def test_a_label_left_empty_falls_back_to_the_whole_leaf():
    assert labels("watchers", ["watchers"]) == {"watchers": "watchers"}


def test_a_label_too_short_to_tell_keeps_its_whole_leaf():
    found = labels("shop", ["shop-hq", "billing/soak-testing"])
    assert found["shop-hq"] == "shop hq"
