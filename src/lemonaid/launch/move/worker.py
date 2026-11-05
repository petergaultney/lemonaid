"""Run independently of a calling lemon that may be the one moving."""

import sys

from .coordinator import run

run(sys.argv[1])
