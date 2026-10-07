import pytest

from lemonaid import go


@pytest.mark.parametrize(
    "url",
    [
        "lemonaid://other/id",
        "lemonaid://go/a/b",
        "lemonaid://go/a?x=y",
        "lemonaid://go/%1B",
        "lemonaid://go/",
        "https://go/id",
    ],
)
def test_malformed_url_is_rejected(url):
    with pytest.raises(ValueError):
        go._target(url)
