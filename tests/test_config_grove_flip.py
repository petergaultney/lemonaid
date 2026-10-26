from lemonaid import config


def test_the_flip_key_cannot_be_one_that_picks_or_one_the_grove_uses(capsys):
    assert config._grove_flip_key("\\") == "\\"
    assert config._grove_flip_key("f5") == "f5"
    for taken in ("a", "S", "3", ".", " ", "/", "?", "escape", "Tab", "", 7):
        assert config._grove_flip_key(taken) == ";"
    assert "grove_flip_key" in capsys.readouterr().err


def test_flip_is_hold_or_toggle(capsys):
    assert config._grove_flip("toggle") == "toggle"
    assert config._grove_flip("press") == "hold"
    assert "grove_flip" in capsys.readouterr().err
