import collections
import importlib
import pkgutil

from lemonaid.inbox import migrations


def test_every_migration_has_its_own_version_and_its_file_names_it():
    found = {
        name: importlib.import_module(f"{migrations.__name__}.{name}").VERSION
        for _, name, is_package in pkgutil.iter_modules(migrations.__path__)
        if name.startswith("m") and not is_package
    }
    shared = {v: n for v, n in collections.Counter(found.values()).items() if n > 1}

    assert not shared, f"versions used by more than one migration: {shared}"
    assert {name: v for name, v in found.items() if int(name[1:4]) != v} == {}
