from lemonaid import config


def test_group_colors_keep_only_hex_colours(capsys) -> None:
    parsed = config._parse_config(
        {"tui": {"group_colors": {"oria": "#112233", "mops": "green", "relay": 3}}}
    )

    assert parsed.tui.group_colors == {"oria": "#112233"}
    assert "'mops'" in capsys.readouterr().err
