from lemonaid.comments import records


def _nested(depth: int, innermost: object) -> dict[str, object]:
    value = innermost
    for _ in range(depth):
        value = [value]
    return {"id": "Deep", "extra": value}


def test_the_unicode_check_walks_any_depth_without_recursion() -> None:
    assert records._is_unicode(_nested(10_000, "fine")) is True
    assert records._is_unicode(_nested(10_000, "\ud800")) is False
