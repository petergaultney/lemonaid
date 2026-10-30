from lemonaid.hooks import context_docs


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_imports_follow_their_importer_depth_first(tmp_path):
    root = _write(tmp_path / "root.md", "@a.md\n@sub/b.md\n")
    _write(tmp_path / "a.md", "alpha\n@nested.md")
    _write(tmp_path / "nested.md", "nested")
    _write(tmp_path / "sub" / "b.md", "beta")

    text = context_docs.expand(root)

    order = [
        text.index(f"Contents of {tmp_path / p}:")
        for p in ("root.md", "a.md", "nested.md", "sub/b.md")
    ]
    assert order == sorted(order)
    assert "alpha" in text and "nested" in text and "beta" in text


def test_escaped_spaces_and_home_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(tmp_path / "My Docs" / "rules.md", "RULES")
    root = _write(tmp_path / "root.md", r"@~/My\ Docs/rules.md")

    assert "RULES" in context_docs.expand(root)


def test_a_cycle_includes_each_file_once(tmp_path):
    root = _write(tmp_path / "a.md", "A\n@b.md")
    _write(tmp_path / "b.md", "B\n@a.md")

    text = context_docs.expand(root)

    assert text.count("Contents of") == 2


def test_code_and_missing_imports_are_skipped(tmp_path):
    root = _write(
        tmp_path / "root.md",
        "mail me@example.com, ping `@name`\n```\n@fenced.md\n```\n@gone.md\n@real.md\n",
    )
    _write(tmp_path / "fenced.md", "FENCED")
    _write(tmp_path / "real.md", "REAL")

    text = context_docs.expand(root)

    assert "REAL" in text
    assert "FENCED" not in text
    assert text.count("Contents of") == 2


def test_imports_stop_at_the_depth_limit(tmp_path):
    for n in range(context_docs.MAX_DEPTH + 2):
        _write(tmp_path / f"{n}.md", f"level-{n}\n@{n + 1}.md")

    text = context_docs.expand(tmp_path / "0.md")

    assert f"level-{context_docs.MAX_DEPTH}" in text
    assert f"level-{context_docs.MAX_DEPTH + 1}" not in text


def test_an_unreadable_root_gives_nothing(tmp_path):
    assert context_docs.expand(tmp_path / "missing.md") == ""


def test_code_examples_stay_literal(tmp_path):
    root = _write(
        tmp_path / "root.md",
        "````md\n```\n@nested-fence.md\n```\n````\n\nspan `starts here\n@span.md ends` here\n\n@real.md\n",
    )
    for name in ("nested-fence.md", "span.md", "real.md"):
        _write(tmp_path / name, name.upper())

    text = context_docs.expand(root)

    assert "REAL.MD" in text
    assert "NESTED-FENCE.MD" not in text
    assert "SPAN.MD" not in text


def test_unresolvable_imports_are_skipped(tmp_path):
    (tmp_path / "loop.md").symlink_to(tmp_path / "loop.md")
    root = _write(tmp_path / "root.md", "@loop.md\n@~lemonaid-no-such-user/rules.md\n@real.md\n")
    _write(tmp_path / "real.md", "REAL")

    text = context_docs.expand(root)

    assert "REAL" in text
    assert text.count("Contents of") == 2
