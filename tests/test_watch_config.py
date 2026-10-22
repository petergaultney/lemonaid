import pytest

from lemonaid import config


@pytest.mark.parametrize("outdated", [False, True])
@pytest.mark.parametrize("resolved", [False, True])
def test_thread_filters_load_from_toml(tmp_path, outdated, resolved):
    path = tmp_path / "config.toml"
    path.write_text(
        f"[watch.pr]\nskip_outdated = {str(outdated).lower()}\n"
        f"skip_resolved = {str(resolved).lower()}\n"
    )

    filters = config.load_config(path).watch.pr

    assert filters.skip_outdated is outdated
    assert filters.skip_resolved is resolved


def test_missing_config_includes_all_threads(tmp_path):
    filters = config.load_config(tmp_path / "missing.toml").watch.pr

    assert filters.skip_outdated is False
    assert filters.skip_resolved is False


@pytest.mark.parametrize("key", ["skip_outdated", "skip_resolved"])
def test_invalid_filter_warns_and_includes_threads(tmp_path, capsys, key):
    path = tmp_path / "config.toml"
    path.write_text(f'[watch.pr]\n{key} = "false"\n')

    filters = config.load_config(path).watch.pr

    assert getattr(filters, key) is False
    assert f"[watch.pr] {key} must be a boolean" in capsys.readouterr().err


def test_roles_and_debounce_load_from_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[watch]\ngithub_debounce = 60\n\n[watch.roles.parent]\nwake = ["state", "head"]\n'
    )

    watch = config.load_config(path).watch

    assert watch.github_debounce == 60
    assert watch.roles == {"parent": frozenset({"state", "head"})}


def test_an_unknown_role_or_kind_warns_and_keeps_the_default(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[watch.roles.lead]\nwake = []\n\n[watch.roles.parent]\nwake = ["pushes"]\n')

    assert config.load_config(path).watch.roles == {}
    err = capsys.readouterr().err
    assert "[watch.roles.lead] is ignored" in err
    assert "[watch.roles.parent] wake must be a list" in err
