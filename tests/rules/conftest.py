import types

import pytest

from lemonaid.rules import end_of_turn


@pytest.fixture(autouse=True)
def _not_a_print_session(monkeypatch):
    """The check leaves `claude -p` sessions alone, and the suite may run under one."""
    monkeypatch.setattr(
        end_of_turn, "print_mode", types.SimpleNamespace(is_print_session=lambda: False)
    )
