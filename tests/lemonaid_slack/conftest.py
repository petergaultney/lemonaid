import pytest

from lemonaid.inbox import db


@pytest.fixture(autouse=True)
def lemonaid_shares_the_test_database(monkeypatch):
    """The plugin writes inbox rows by running `lemonaid inbox`, in another process."""
    monkeypatch.setenv("LEMONAID_DB", str(db.get_db_path()))
