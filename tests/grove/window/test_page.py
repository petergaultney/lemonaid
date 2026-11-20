from lemonaid.grove.window import page


def test_the_page_carries_its_scripts_inline():
    html = page.html()

    assert '.js"></script>' not in html
    assert "function layOut(" in html
    assert html.index("function layOut(") < html.index("layOut(DATA.blocks")
    assert "function showMenu(" in html
