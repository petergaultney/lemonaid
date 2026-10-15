"""The WezTerm module lemonaid writes, and whether wezterm.lua loads it."""

from lemonaid.terminal import wezterm_rules


def test_the_regex_is_a_lua_long_string_that_contains_its_own_brackets():
    text = wezterm_rules.module_text(r"a[^\]]]=]b", "/bin/lemonaid")

    assert "regex = [==[a[^\\]]]=]b]==]," in text
    assert "format = PREFIX .. '$1'," in text


def test_wezterm_lua_requires_the_module_only_once_its_lines_are_added(tmp_path):
    (tmp_path / "wezterm.lua").write_text("local config = {}\nreturn config\n")
    assert not wezterm_rules.requires_module(tmp_path)

    (tmp_path / "wezterm.lua").write_text(wezterm_rules.REQUIRE)
    assert wezterm_rules.requires_module(tmp_path)
