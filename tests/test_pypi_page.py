"""PyPI renders the package readme with no base URL, so a relative link there is broken."""

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def _project() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text())["project"]


def test_the_sidebar_links_to_github():
    urls = _project()["urls"]

    assert set(urls) >= {"Homepage", "Documentation", "Changelog", "Issues"}
    assert all(u.startswith("https://github.com/petergaultney/lemonaid") for u in urls.values())


def test_the_pypi_readme_links_only_absolute_urls():
    text = (_ROOT / _project()["readme"]).read_text()
    targets = re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'src="([^"]+)"', text)

    assert targets
    assert [t for t in targets if not t.startswith("https://")] == []
