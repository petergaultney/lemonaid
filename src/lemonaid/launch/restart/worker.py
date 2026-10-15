"""Run independently of a calling lemon that may itself be restarted."""

import sys

from .coordinator import run

run(sys.argv[1])
