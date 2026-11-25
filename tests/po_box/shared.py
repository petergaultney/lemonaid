from pathlib import Path


def configure_po_box(monkeypatch, tmp_path: Path, owner: str = "sam") -> Path:
    root = tmp_path / "lemon-post"
    root.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(f'[po-box]\nroot = "{root}"\nowner = "{owner}"\n')
    monkeypatch.setenv("LEMONAID_CONFIG", str(config))
    return root
