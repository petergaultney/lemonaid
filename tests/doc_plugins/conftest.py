import pytest

from lemonaid.doc_plugins import run


@pytest.fixture(autouse=True)
def _fresh_plugins():
    """Each test starts its plugins anew, and a failure in one test doesn't hold off another."""
    yield
    run.stop_all()
    run._failed_at.clear()
