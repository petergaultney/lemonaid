import pytest

from lemonaid.plugins import processes


@pytest.fixture(autouse=True)
def _fresh_plugins():
    """Each test starts its plugins anew, and a failure in one test doesn't hold off another."""
    yield
    processes.close()
    processes._failed_at.clear()
