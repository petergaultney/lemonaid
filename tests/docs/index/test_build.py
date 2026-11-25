import os
from pathlib import Path

from lemonaid.docs import frontmatter, index

from ..shared import doc


def test_only_docs_that_declare_something_are_indexed_in_root_order(tmp_path):
    first, second = tmp_path / "general", tmp_path / "work"
    doc(second, "deploy.md", {"package": "work"})
    doc(first, "plain.md", {"type": "Notes"})
    doc(first, "no-frontmatter.md")
    doc(first, "prose.md", {"load-when": [{"command": "^git commit"}]})
    doc(first, ".hidden/secret.md", {"package": "core"})

    docs = index.build([first, second], tmp_path / "index.json")

    assert [d.path.name for d in docs] == ["prose.md", "deploy.md"]


def test_a_rebuild_reads_only_the_docs_that_changed(tmp_path, monkeypatch):
    root, cache = tmp_path / "docs", tmp_path / "index.json"
    kept = doc(root, "kept.md", {"package": "core"})
    changed = doc(root, "changed.md", {"package": "core"})
    index.build([root], cache)
    read: list[Path] = []
    real = frontmatter.fields
    monkeypatch.setattr(frontmatter, "fields", lambda path: read.append(path) or real(path))

    doc(root, "changed.md", {"package": "grove"})
    later = changed.stat().st_mtime + 10
    os.utime(changed, (later, later))
    docs = index.build([root], cache)

    assert read == [changed]
    assert {d.path: d.packages for d in docs} == {kept: ("core",), changed: ("grove",)}
    assert index.read(cache) == docs


def test_a_package_index_is_named_for_its_file(tmp_path):
    root = tmp_path / "docs"
    doc(root, "packages/python.md", {"package-for": [{"file": "pyproject.toml"}]})

    (package,) = index.build([root], tmp_path / "index.json")

    assert frontmatter.package_name(package) == "python"
    assert package.lemons == ({"file": "pyproject.toml"},)


def test_a_root_may_be_a_single_doc(tmp_path):
    folder = tmp_path / "docs"
    doc(folder, "deploy.md", {"package": "work"})
    single = doc(tmp_path / "vault", "for-lemons.md", {"package": "core"})
    doc(tmp_path / "vault", "beside.md", {"package": "core"})

    docs = index.build([single, folder], tmp_path / "index.json")

    assert [d.path.name for d in docs] == ["for-lemons.md", "deploy.md"]
