from lemonaid import config


def test_group_colors_keep_only_hex_colors(capsys) -> None:
    parsed = config._parse_config(
        {"tui": {"group_colors": {"webapp": "#112233", "billing": "green", "relay": 3}}}
    )

    assert parsed.tui.group_colors == {"webapp": "#112233"}
    assert "'billing'" in capsys.readouterr().err
