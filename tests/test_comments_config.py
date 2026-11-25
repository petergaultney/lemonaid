import getpass

from lemonaid import comments_config


def test_your_comments_are_signed_with_the_configured_author() -> None:
    assert comments_config.parse({"author": "Caleb Gregory"}).signature() == "Caleb Gregory"


def test_without_an_author_your_comments_are_signed_with_your_login(capsys) -> None:
    assert comments_config.parse({}).signature() == getpass.getuser()
    assert comments_config.parse({"author": "  "}).signature() == getpass.getuser()
    assert "[comments] author" in capsys.readouterr().err


def test_a_comments_value_that_isn_t_a_table_is_ignored(capsys) -> None:
    assert comments_config.parse("unexpected").signature() == getpass.getuser()
    assert "[comments] must be a table" in capsys.readouterr().err
