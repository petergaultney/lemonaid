from lemonaid.grove.draw import canvas, list_spot, tag_fit

W, H = 54, 4  # a list's width and height
CROWN = (95, 20, 11, 5)
TAG = tag_fit.Fitted((" t  the tree ",), 96, 26, (100, 25))
FOOTPRINT = list_spot.footprint(CROWN, TAG)


def _spot(taken=(), others=()) -> list_spot.Rect:
    x, y = list_spot.spot(canvas.blank(200, 60), CROWN, TAG, others, W, H, [FOOTPRINT, *taken])
    return x, y, W, H


def test_a_list_hangs_from_its_tag_so_the_tag_is_its_title():
    x, y, _, _ = _spot()
    assert (x + 1, y) == (TAG.x, TAG.y)


def test_a_list_with_no_room_below_goes_above_its_crown_before_beside_it():
    below = [(0, TAG.y + 1, 200, 20)]
    x, y, _, _ = _spot(below)
    assert y + H < CROWN[1] and x + 1 == TAG.x


def test_a_list_with_no_room_below_or_above_goes_right_of_its_crown_never_left():
    hemmed = [(0, 0, 200, CROWN[1] - 1), (0, TAG.y + 1, 200, 20)]
    x, y, _, _ = _spot(hemmed)
    assert x == CROWN[0] + CROWN[2] + list_spot.GAP and CROWN[1] <= y < CROWN[1] + CROWN[3]


def test_a_list_whose_title_would_sit_nearer_another_tree_goes_where_it_reads_as_its_own():
    below = (0, TAG.y + 1, 200, 20)
    neighbor = (60, 12, 32, 5)  # up and to the left, nearer the title above the crown than it is
    x, y, _, _ = _spot([below, neighbor], [neighbor])
    title = (x + 1, y, len(TAG.lines[0]), 1)
    assert list_spot._apart(title, FOOTPRINT) < list_spot._apart(title, neighbor)
    assert x == CROWN[0] + CROWN[2] + list_spot.GAP


def test_a_list_with_no_room_at_its_tree_goes_to_the_nearest_free_room_level_with_it():
    hemmed = [(0, 0, 200, CROWN[1] - 1), (0, TAG.y + 1, 200, 20), (CROWN[0] + CROWN[2], 0, 40, 60)]
    x, y = list_spot.spot(canvas.blank(200, 60), CROWN, TAG, (), W, H, [FOOTPRINT, *hemmed])
    assert x + W <= CROWN[0] - list_spot.GAP + 3 and CROWN[1] - H <= y <= CROWN[1] + CROWN[3]


def test_a_list_may_hang_to_the_left_of_its_tag_so_its_title_still_sits_under_the_tree():
    right_taken = [(TAG.x + len(TAG.lines[0]) + 1 + list_spot.GAP, TAG.y, 100, H + 2)]
    x, y = list_spot.spot(canvas.blank(200, 60), CROWN, TAG, (), W, H, [FOOTPRINT, *right_taken])
    tlen = len(TAG.lines[0])
    assert y == TAG.y and x + W == TAG.x + tlen + 1
    assert list_spot.title_at(TAG.x, x, W, tlen) == TAG.x


def test_a_list_covering_a_neighbor_at_its_tree_beats_a_free_spot_far_across_the_screen():
    crowded = [(0, 0, 300, 60)]  # all the room within 200 columns is taken
    x, y = list_spot.spot(canvas.blank(400, 60), CROWN, TAG, (), W, H, [FOOTPRINT, *crowded])
    assert y == TAG.y and abs(x - TAG.x) < W
