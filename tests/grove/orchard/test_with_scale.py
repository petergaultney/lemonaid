from lemonaid.grove.layout import orchard


def test_switching_scale_and_back_restores_each_layout():
    blocks_scale = {
        "plots": {"g": {"x": 1}},
        "trees": {"g": {}},
        "roads": [[0, 0]],
        "packhouse": True,
    }

    trees = orchard.with_scale(blocks_scale, True)
    assert orchard.is_trees(trees) and trees["plots"] == {} and "roads" not in trees
    trees["plots"]["g"] = {"x": 9}

    back = orchard.with_scale(trees, False)
    assert {k: back[k] for k in ("plots", "trees", "roads", "packhouse")} == blocks_scale
    assert orchard.with_scale(back, True)["plots"] == {"g": {"x": 9}}
