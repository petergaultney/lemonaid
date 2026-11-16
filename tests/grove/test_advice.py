from lemonaid.grove.layout import advice, arrange
from tests.grove.shared import NOW, block, plot_data, stream_saved, tree

_SIZE = (214, 63)


def _advised(spots: dict[str, tuple[int, int]], **plot: object) -> list[advice.Advice]:
    grove = (block("a", "1", *(tree(key) for key in spots)),)
    saved = stream_saved(
        {"a": plot_data(20, 2, 120, 26, **plot)},
        {"a": {key: {"letter": key, "x": x, "y": y} for key, (x, y) in spots.items()}},
    )
    return advice.advise(grove, arrange.arrange(grove, saved, NOW)[0], _SIZE)


def test_trees_far_apart_and_staggered_draw_no_warnings():
    assert _advised({"s": (20, 6), "t": (80, 16)}) == []


def test_neighbors_on_one_row_are_warned_about():
    kinds = {(a.letter, a.kind) for a in _advised({"s": (40, 10), "t": (48, 10)})}

    assert ("s", "level") in kinds


def test_a_trunk_off_a_rounded_corner_is_warned_about():
    advised = _advised({"s": (2, 1)}, roundness=1.5)

    assert ("s", "off-ground") in {(a.letter, a.kind) for a in advised}


def test_a_lead_with_a_tree_nearer_the_packhouse_is_warned_about():
    grove = (block("", "0", tree("hq")), block("a", "1", tree("l", lead=True), tree("s")))
    saved = stream_saved(
        {"": plot_data(0, 2, 16, 8, texture="house"), "a": plot_data(20, 2, 120, 26)},
        {
            "a": {
                ":lead": {"letter": "l", "x": 100, "y": 10},
                "s": {"letter": "s", "x": 10, "y": 10},
            }
        },
    )

    advised = advice.advise(grove, arrange.arrange(grove, saved, NOW)[0], _SIZE)

    assert ("l", "lead-far") in {(a.letter, a.kind) for a in advised}
