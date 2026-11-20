import pytest

from lemonaid.lsp import positions


@pytest.mark.parametrize(
    ("text", "offset", "position"),
    [
        ("ab\ncd", 4, (1, 1)),
        ("ab\r\ncd", 5, (1, 1)),
        ("ab\rcd", 4, (1, 1)),
        ("ab\n", 3, (1, 0)),
        ("\U0001f34bx\n", 1, (0, 2)),
    ],
)
def test_lines_break_at_lf_crlf_and_cr_and_columns_count_utf16_units(
    text, offset, position
) -> None:
    codec = positions.Codec(text)

    assert codec.position(offset) == position
    assert codec.offset(positions.Position(*position)) == offset


@pytest.mark.parametrize(("encoding", "column"), [("utf-8", 6), ("utf-16", 3), ("utf-32", 2)])
def test_columns_count_in_the_agreed_encoding(encoding, column) -> None:
    codec = positions.Codec("é\U0001f34bx", encoding)

    assert codec.position(2) == (0, column)


def test_a_position_past_its_line_is_the_end_of_that_line() -> None:
    codec = positions.Codec("ab\r\ncd")

    assert codec.offset(positions.Position(0, 99)) == 2
    assert codec.offset(positions.Position(9, 0)) == 6
