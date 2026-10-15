"""Detached restart coordinator entry point."""

import sys

from . import coordinator, supervisor

if __name__ == "__main__":
    (coordinator.run if "--coordinate" in sys.argv else supervisor.run)(sys.argv[1])
