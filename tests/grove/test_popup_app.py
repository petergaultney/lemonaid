from lemonaid.grove import popup_app


def test_the_sidebar_and_the_top_strip_want_the_popup():
    assert popup_app.wants_popup(60, 80)
    assert popup_app.wants_popup(300, 20)


def test_a_full_window_does_not():
    assert not popup_app.wants_popup(popup_app.MAP_WIDTH, popup_app.MAP_HEIGHT)
