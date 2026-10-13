import colorsys
import itertools

from lemonaid import palette


def _rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def test_slots_are_saturated_and_readable_on_black() -> None:
    for slot in palette.SLOTS:
        assert colorsys.rgb_to_hls(*_rgb(slot))[2] > 0.5, slot
        assert (palette._luminance(*_rgb(slot)) + 0.05) / 0.05 >= 6.5, slot


def test_slots_leave_no_wide_gap_in_the_hue_wheel() -> None:
    hues = sorted(colorsys.rgb_to_hls(*_rgb(s))[0] * 360 for s in palette.SLOTS)
    gaps = [b - a for a, b in itertools.pairwise(hues)] + [hues[0] + 360 - hues[-1]]

    assert max(gaps) <= 30


def test_no_two_slots_look_alike() -> None:
    slots = palette.SLOTS

    assert min(palette.distance(a, b) for i, a in enumerate(slots) for b in slots[:i]) >= (
        palette.MIN_DISTANCE
    )


def test_color_for_is_stable() -> None:
    assert palette.color_for("lemonaid") == palette.color_for("lemonaid")
    assert palette.color_for("lemonaid") in palette.SLOTS


def test_groups_with_the_same_hash_slot_neighbourhood_get_apart_colors() -> None:
    names = [f"group-{i}" for i in range(14)]

    given = palette.assign_groups(names, {})

    colors = list(given.values())
    assert min(palette.distance(a, b) for i, a in enumerate(colors) for b in colors[:i]) >= (
        palette.GROUP_MIN_DISTANCE
    )


def test_a_groups_color_depends_on_the_set_of_groups_not_their_order() -> None:
    names = ["oria", "mops", "relay", "watchers", "lemonaid"]

    assert palette.assign_groups(names, {}) == palette.assign_groups(reversed(names), {})


def test_a_group_alone_keeps_its_hash_slot() -> None:
    assert palette.assign_groups(["oria"], {}) == {"oria": palette.color_for("oria")}


def test_a_pinned_color_wins_and_others_keep_clear_of_it() -> None:
    pinned = palette.color_for("mops")

    given = palette.assign_groups(["oria", "mops"], {"mops": pinned, "gone": "#ffffff"})

    assert given["mops"] == pinned
    assert "gone" not in given
    assert palette.distance(given["oria"], pinned) >= palette.GROUP_MIN_DISTANCE
