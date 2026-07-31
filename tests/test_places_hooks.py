"""Place roots delegate directory management to configured shell commands.

The point of these tests is that lemonaid never needs to know what tool is on the
other end - only that it emits lines.
"""

from pathlib import Path

from lemonaid.config import PlaceRoot, PlacesConfig, _parse_config
from lemonaid.places import hooks


def test_substitute_quotes_values_so_they_cannot_extend_the_command():
    assert hooks.substitute("tool {key}", key="a; rm -rf /") == "tool 'a; rm -rf /'"


def test_substitute_fills_both_placeholders():
    assert hooks.substitute("t {key} {dir}", key="k", directory="/d") == "t k /d"


def test_unset_hook_runs_nothing(tmp_path):
    assert hooks.run_lines(PlaceRoot(path=tmp_path), "") == []


def test_hooks_are_run_through_a_shell(tmp_path):
    """Emitting one path per line is often most natural as a pipeline."""
    root = PlaceRoot(path=tmp_path, list="printf 'a\\nb\\n' | grep b")

    assert hooks.run_lines(root, root.list) == ["b"]


def test_failing_hook_yields_nothing(tmp_path):
    assert hooks.run_lines(PlaceRoot(path=tmp_path), "exit 3") == []


def test_list_returns_absolute_directories(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    root = PlaceRoot(path=tmp_path, list=f"printf '{tmp_path}/one\\n{tmp_path}/two\\n'")

    assert hooks.list_directories(root) == [tmp_path / "one", tmp_path / "two"]


def test_list_resolves_relative_paths_against_the_root(tmp_path):
    (tmp_path / "rel").mkdir()
    root = PlaceRoot(path=tmp_path, list="echo rel")

    assert hooks.list_directories(root) == [tmp_path / "rel"]


def test_list_drops_paths_that_are_not_directories(tmp_path):
    """A stale listing shouldn't produce rows that can't be opened."""
    (tmp_path / "real").mkdir()
    root = PlaceRoot(path=tmp_path, list="printf 'real\\nvanished\\n'")

    assert hooks.list_directories(root) == [tmp_path / "real"]


def test_list_takes_only_the_path_from_a_tab_labelled_line(tmp_path):
    (tmp_path / "wt").mkdir()
    root = PlaceRoot(path=tmp_path, list="printf 'wt\\tsome label\\n'")

    assert hooks.list_directories(root) == [tmp_path / "wt"]


def test_directory_for_key_uses_the_path_of_hook(tmp_path):
    (tmp_path / "found").mkdir()
    root = PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/found")

    assert hooks.directory_for_key(root, "anything") == tmp_path / "found"


def test_directory_for_key_is_none_when_it_does_not_exist(tmp_path):
    root = PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/nope")

    assert hooks.directory_for_key(root, "k") is None


def test_create_reports_the_directory_via_path_of(tmp_path):
    """create can't report its own directory - the tool usually only cd's."""
    root = PlaceRoot(
        path=tmp_path,
        create="mkdir -p made",
        path_of=f"echo {tmp_path}/made",
    )

    assert hooks.create(root, "made", timeout=10) == tmp_path / "made"


def test_create_without_a_hook_does_nothing(tmp_path):
    assert hooks.create(PlaceRoot(path=tmp_path), "k", timeout=10) is None


def test_destroy_declines_without_a_hook(tmp_path):
    assert hooks.destroy(PlaceRoot(path=tmp_path), "k", timeout=10) is False


def test_inspect_passes_the_directory_through(tmp_path):
    root = PlaceRoot(path=tmp_path, inspect="echo checked {dir}")

    assert hooks.inspect(root, Path("/some/where")) == "checked /some/where"


def test_root_for_picks_the_innermost_configured_root(tmp_path):
    outer = PlaceRoot(path=tmp_path)
    inner = PlaceRoot(path=tmp_path / "nested")
    (tmp_path / "nested" / "deep").mkdir(parents=True)

    places = PlacesConfig(roots=[outer, inner])

    assert places.root_for(tmp_path / "nested" / "deep") is inner
    assert places.root_for(tmp_path) is outer


def test_root_for_is_none_outside_every_root(tmp_path):
    assert PlacesConfig(roots=[PlaceRoot(path=tmp_path / "a")]).root_for(tmp_path / "b") is None


def test_a_root_with_no_hooks_is_valid():
    """A plain clone has nothing to list, create, or destroy."""
    config = _parse_config({"places": {"roots": [{"path": "~/somewhere"}]}})

    assert len(config.places.roots) == 1
    assert config.places.roots[0].list == ""


def test_roots_without_a_path_are_ignored():
    config = _parse_config({"places": {"roots": [{"list": "x"}, {"path": "/ok"}]}})

    assert [str(r.path) for r in config.places.roots] == ["/ok"]


def test_root_paths_are_user_expanded():
    config = _parse_config({"places": {"roots": [{"path": "~/x"}]}})

    assert config.places.roots[0].path == Path.home() / "x"


def test_nested_keys_survive_the_listing(tmp_path):
    """Keys with a separator are common; the listing must not flatten them."""
    (tmp_path / "release" / "202608").mkdir(parents=True)
    root = PlaceRoot(path=tmp_path, list="echo release/202608")

    assert hooks.list_directories(root) == [tmp_path / "release" / "202608"]


def test_protected_keys_default_to_the_usual_trunk_names():
    config = _parse_config({"places": {"roots": [{"path": "/r"}]}})

    assert config.places.roots[0].is_protected("main")
    assert config.places.roots[0].is_protected("master")


def test_protected_keys_can_be_overridden_per_root():
    config = _parse_config({"places": {"roots": [{"path": "/r", "protected": ["trunk"]}]}})

    assert config.places.roots[0].is_protected("trunk")
    assert not config.places.roots[0].is_protected("main")


def test_protection_can_be_turned_off_explicitly():
    config = _parse_config({"places": {"roots": [{"path": "/r", "protected": []}]}})

    assert not config.places.roots[0].is_protected("main")
