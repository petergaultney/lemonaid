from lemonaid import web_config


def test_parse_reads_the_keys_and_defaults_the_rest():
    assert web_config.parse({"prefix": "C-a"}) == web_config.WebConfig("C-a", "prefix", "h", "b")


def test_parse_warns_and_keeps_the_default_for_a_blank_key(capsys):
    assert web_config.parse({"literal": " "}).literal == "h"
    assert "[web] literal" in capsys.readouterr().err
