from lemonaid import config


def test_the_select_key_may_be_tab_or_any_key_the_grove_leaves_free(capsys):
    assert config._grove_select_key("tab", ";") == "tab"
    assert config._grove_select_key("`", ";") == "`"
    assert config._grove_select_key("f6", ";") == "f6"
    for taken in ("s", "5", ".", ";", "/", "escape", "enter", "backspace", "home", "alt+3", "!"):
        assert config._grove_select_key(taken, ";") == "tab"
    assert "grove_select_key" in capsys.readouterr().err
