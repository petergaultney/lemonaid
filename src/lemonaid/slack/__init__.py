"""Slack integration for lemonaid.

Provides deep linking to Slack channels/DMs from macOS notifications.
Requires a manually-generated mappings file with channel IDs.

Mappings are stored in ~/.local/state/lemonaid/slack-mappings.json
See docs/macos.md for instructions on generating them.
"""

from .mappings import ChannelLookup, get_mappings_path, load_mappings, lookup_channel

__all__ = ["ChannelLookup", "get_mappings_path", "load_mappings", "lookup_channel"]
