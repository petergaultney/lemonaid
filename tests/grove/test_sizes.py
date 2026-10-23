from lemonaid.grove.layout import sizes
from lemonaid.grove.model import Plot

from .shared import DAY, NOW, block, tree


def test_young_trees_are_smaller():
    assert (
        sizes.growth(NOW - 3600, NOW)
        < sizes.growth(NOW - 2 * DAY, NOW)
        < sizes.growth(NOW - 9 * DAY, NOW)
    )


def test_a_crowded_block_shrinks_its_trees_within_limits():
    many = block("b", "1", *(tree(f"t{i}") for i in range(12)))
    one = block("b", "1", tree("t0"))
    plot = Plot(0, 0, 40, 12, 3.4, 1, "rows")
    grown = {t.key: 1.0 for t in many.trees}
    assert 0.68 <= sizes.crowding(plot, many, grown) < sizes.crowding(plot, one, grown) <= 1.6
