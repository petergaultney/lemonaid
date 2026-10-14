"""Loads the release scripts in scripts/, which import each other by bare module name."""

import importlib.util
import sys
import types
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


def load(file_name: str, module_name: str) -> types.ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


changefiles = load("changefiles.py", "changefiles")
changecheck = load("changecheck.py", "changecheck")
