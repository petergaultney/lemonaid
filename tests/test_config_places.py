"""Parsing the [places] config.

A key that silently fails to parse is the worst outcome here - protection that
looks configured but isn't would only surface by destroying something.
"""

from pathlib import Path

from lemonaid.config import PlaceRoot, _parse_config


def test_a_root_parses_its_hooks():
    config = _parse_config(
        {
            "places": {
                "roots": [
                    {
                        "path": "~/work/somerepo",
                        "list": "git worktree list",
                        "path_of": "wt path {key}",
                        "create": "wt co {key}",
                        "destroy": "wt rm -f {key}",
                        "inspect": "wt status {dir}",
                    }
                ]
            }
        }
    )

    root = config.places.roots[0]
    assert root.path == Path("~/work/somerepo").expanduser()
    assert root.create == "wt co {key}"
    assert root.inspect == "wt status {dir}"


def test_a_root_with_no_hooks_is_a_plain_clone():
    config = _parse_config({"places": {"roots": [{"path": "/tmp/plain"}]}})

    root = config.places.roots[0]
    assert root.list == ""
    assert root.destroy == ""


def test_a_root_without_a_path_is_skipped():
    config = _parse_config({"places": {"roots": [{"create": "x"}, {"path": "/tmp/ok"}]}})

    assert [r.path for r in config.places.roots] == [Path("/tmp/ok")]


def test_protected_keys_default_when_unset():
    config = _parse_config({"places": {"roots": [{"path": "/tmp/x"}]}})

    assert config.places.roots[0].protected == PlaceRoot.protected


def test_protected_keys_are_overridable():
    config = _parse_config({"places": {"roots": [{"path": "/tmp/x", "protected": ["trunk"]}]}})

    root = config.places.roots[0]
    assert root.is_protected("trunk")
    assert not root.is_protected("main")


def test_an_empty_protected_list_is_honored():
    """Explicitly opting out must not silently fall back to the default."""
    config = _parse_config({"places": {"roots": [{"path": "/tmp/x", "protected": []}]}})

    assert not config.places.roots[0].is_protected("main")


def test_protected_sessions_parse():
    config = _parse_config({"places": {"protected_sessions": ["main", "lemonaid"]}})

    assert config.places.is_protected_session("main")
    assert config.places.is_protected_session("lemonaid")
    assert not config.places.is_protected_session("feat/thing")


def test_no_sessions_are_protected_by_default():
    config = _parse_config({"places": {"roots": [{"path": "/tmp/x"}]}})

    assert not config.places.is_protected_session("main")


def test_protected_sessions_coexist_with_roots():
    """They're separate settings; declaring one must not drop the other."""
    config = _parse_config(
        {"places": {"protected_sessions": ["main"], "roots": [{"path": "/tmp/x"}]}}
    )

    assert config.places.is_protected_session("main")
    assert len(config.places.roots) == 1


def test_no_places_section_at_all():
    config = _parse_config({})

    assert config.places.roots == []
    assert config.places.protected_sessions == ()
