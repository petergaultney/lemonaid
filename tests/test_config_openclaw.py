"""Tests for OpenClaw configuration parsing."""

from lemonaid.config import OpenclawConfig, _parse_config


def test_openclaw_config_defaults():
    """OpenclawConfig has expected defaults."""
    oc = OpenclawConfig()
    assert oc.remote_host is None


def test_parse_openclaw_remote_host():
    """Parsing config with openclaw.remote_host sets the value."""
    data = {"openclaw": {"remote_host": "lemon-grove"}}
    config = _parse_config(data)
    assert config.openclaw.remote_host == "lemon-grove"


def test_parse_openclaw_remote_host_user_at_host():
    """Parsing config with user@host format works."""
    data = {"openclaw": {"remote_host": "lemonlime@lemon-grove"}}
    config = _parse_config(data)
    assert config.openclaw.remote_host == "lemonlime@lemon-grove"


def test_parse_openclaw_missing_section():
    """Config without [openclaw] section uses defaults."""
    data = {"tui": {}}
    config = _parse_config(data)
    assert config.openclaw.remote_host is None


def test_parse_openclaw_empty_section():
    """Config with empty [openclaw] section uses defaults."""
    data = {"openclaw": {}}
    config = _parse_config(data)
    assert config.openclaw.remote_host is None
