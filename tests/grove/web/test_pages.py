"""The pages `grove serve` sends: each runs the web grove's scripts before its own."""

from lemonaid import web_config
from lemonaid.grove.web import pages


def test_the_grove_gets_the_shim_before_its_own_scripts():
    page = pages.grove(web_config.WebConfig())

    assert page.index("window.pywebview = {api") < page.index("window.groveData = async")


def test_every_page_gets_the_web_keys_before_its_own_scripts():
    keys = web_config.WebConfig(prefix="C-a")
    for page in (pages.grove(keys), pages.lemon(keys), pages.groups(keys)):
        given = page.index(
            'window.groveKeys = {"prefix": "C-a", "home": "prefix", "literal": "h", "brief": "b"}'
        )
        assert given < page.index("<script>", given)


def test_every_page_links_the_icons_that_are_served():
    served = pages.served(web_config.WebConfig())
    for name in ("grove", "lemon", "groups"):
        head = served[name][0].decode().split("</head>")[0]
        assert 'href="icon.svg"' in head and 'href="apple-touch-icon.png"' in head
    assert served["icon.svg"][0].startswith(b"<svg")
    assert served["apple-touch-icon.png"][0].startswith(b"\x89PNG")


def test_a_phone_gets_the_groups_and_a_tablet_the_grove():
    assert pages.for_phone("Mozilla/5.0 (Android 17; Mobile; rv:160.0) Gecko/160.0 Firefox/160.0")
    assert pages.for_phone("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) Mobile/15E148")
    assert not pages.for_phone("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15")
