import collections
import importlib
import pkgutil
import sqlite3
import subprocess
import sys

import pytest

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


def test_a_migration_that_ends_the_lock_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        migrations,
        "discover_migrations",
        lambda: [(1, "a table", lambda conn: conn.executescript("CREATE TABLE t (a)"))],
    )
    conn = sqlite3.connect(tmp_path / "inbox.db")

    with pytest.raises(RuntimeError, match="v1 ended the exclusive transaction"):
        migrations.run_migrations(conn)
    assert migrations.get_current_version(conn) == 0


def test_processes_starting_together_on_a_fresh_database_all_migrate_it(tmp_path):
    code = (
        "import sys; from pathlib import Path; from lemonaid.inbox import db\n"
        "with db.connect(Path(sys.argv[1])): pass\n"
    )
    for attempt in range(5):
        path = tmp_path / f"inbox-{attempt}.db"
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", code, str(path)], stderr=subprocess.PIPE, text=True
            )
            for _ in range(6)
        ]
        failures = [err for p in procs if (err := p.communicate()[1]) and p.returncode]

        assert failures == []
