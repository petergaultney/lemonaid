import pytest

from lemonaid.config import InboxConfig, _parse_config


def test_ungrouped_first_defaults_on():
    assert InboxConfig().ungrouped_first is True
    assert _parse_config({}).inbox.ungrouped_first is True


@pytest.mark.parametrize("enabled", [True, False])
def test_parse_ungrouped_first(enabled):
    assert _parse_config({"inbox": {"ungrouped_first": enabled}}).inbox.ungrouped_first is enabled
