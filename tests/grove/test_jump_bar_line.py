from lemonaid.grove.tui import frame, jump_bar, keys
from lemonaid.grove.tui.frame import Grove

from .keys.test_step import ARRANGEMENT, BIG, BLOCKS, letter


def _grove() -> Grove:
    return Grove(BLOCKS, ARRANGEMENT, {})


def test_the_typed_key_is_drawn_in_its_blocks_color():
    where, _ = keys.step(keys.Where(), "1", BLOCKS, ARRANGEMENT)
    where, _ = keys.step(where, ".", BLOCKS, ARRANGEMENT)
    where, _ = keys.step(where, letter(BIG.key), BLOCKS, ARRANGEMENT)
    line = jump_bar._line(where, _grove())
    typed = line.spans[0]
    assert line.plain[typed.start : typed.end] == f" 1.{letter(BIG.key)} "
    assert typed.style.bgcolor.name == BLOCKS[0].color


def test_the_grove_prompt_draws_the_typed_key_in_its_blocks_color():
    prompt = frame._Prompt(*frame._prompt(keys.Where(block="1", digits="1"), _grove(), "tab"))
    assert (prompt.key, prompt.key_color) == ("1", BLOCKS[0].color)
    assert prompt.label == BLOCKS[0].name and BLOCKS[0].name not in prompt.line


def test_the_group_name_follows_the_typed_key_in_its_blocks_color():
    where, _ = keys.step(keys.Where(), "1", BLOCKS, ARRANGEMENT)
    line = jump_bar._line(where, _grove())
    name = line.spans[1]
    assert line.plain[name.start : name.end] == f" {BLOCKS[0].name}"
    assert name.style.color.name == BLOCKS[0].color


def _typed_states() -> list[keys.Where]:
    where, states = keys.Where(), []
    for key in ("1", ".", letter(BIG.key)):
        where, _ = keys.step(where, key, BLOCKS, ARRANGEMENT)
        states.append(where)
    return states


def test_the_bar_names_the_group_once_in_every_typed_state():
    for where in _typed_states():
        line = jump_bar._line(where, _grove())
        assert line.plain.count(BLOCKS[0].name) == 1
        assert BLOCKS[0].name not in line.plain[: line.spans[0].end]


def test_the_grove_prompt_labels_every_typed_state_without_a_colon():
    for where in _typed_states():
        prompt = frame._Prompt(*frame._prompt(where, _grove(), "tab"))
        assert prompt.label == BLOCKS[0].name and not prompt.line.startswith(":")
