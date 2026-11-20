from lemonaid.grove.window import placement

TERMINAL = (0, 0, 1000, 800)


def test_the_share_is_of_the_terminals_window_that_the_grove_covers():
    assert placement.covered_share(TERMINAL, TERMINAL) == 1.0
    assert placement.covered_share((500, 0, 2000, 2000), TERMINAL) == 0.5
    assert placement.covered_share((1000, 0, 400, 400), TERMINAL) == 0.0  # touching, beside it
    assert placement.covered_share((0, 0, 10, 10), (0, 0, 0, 0)) == 0.0


def test_a_grove_covering_a_tenth_of_the_terminal_is_over_it_and_less_floats():
    assert placement.over_terminal((900, 0, 500, 800), TERMINAL, 0.1)  # its right tenth
    assert not placement.over_terminal((950, 0, 500, 800), TERMINAL, 0.1)
    assert not placement.over_terminal((2000, 0, 800, 600), TERMINAL, 0.1)  # another display
    assert placement.over_terminal((2000, 0, 800, 600), None, 0.1)  # no terminal window found
