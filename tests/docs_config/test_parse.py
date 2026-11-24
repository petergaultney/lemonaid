from pathlib import Path

from lemonaid import docs_config


def test_an_empty_table_is_classic_with_no_root():
    assert docs_config.parse({}) == docs_config.DocsConfig(mode="classic", classic=None)


def test_the_root_expands_home():
    parsed = docs_config.parse({"mode": "packages", "classic": "~/docs/root.md"})

    assert parsed == docs_config.DocsConfig("packages", Path.home() / "docs" / "root.md")


def test_an_unknown_mode_warns_and_is_classic(capsys):
    assert docs_config.parse({"mode": "lean"}).mode == "classic"
    assert "[docs] mode" in capsys.readouterr().err


def test_a_root_that_is_not_a_path_warns_and_is_unset(capsys):
    assert docs_config.parse({"classic": 3}).classic is None
    assert "[docs] classic" in capsys.readouterr().err


def test_roots_and_the_default_branch_check():
    parsed = docs_config.parse({"roots": ["~/docs", "/shared"], "default-branch-check": "true"})

    assert parsed.roots == (Path.home() / "docs", Path("/shared"))
    assert parsed.default_branch_check == "true"


def test_roots_that_are_not_a_list_warn_and_are_empty(capsys):
    assert docs_config.parse({"roots": "~/docs"}).roots == ()
    assert "[docs] roots" in capsys.readouterr().err
