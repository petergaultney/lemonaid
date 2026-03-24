"""Lemonaid OpenClaw integration.

OpenClaw is an open-source personal AI assistant. Sessions are stored at:
~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl

Session index is at:
~/.openclaw/agents/<agentId>/sessions/sessions.json
"""

from . import cli, utils, watcher  # noqa: F401
