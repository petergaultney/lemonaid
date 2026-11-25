from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.docs import frontmatter, lemons
from lemonaid.inbox import db
from lemonaid.lineage import links


def _package(name: str, *items: dict) -> frontmatter.Doc:
    return frontmatter.Doc(path=Path(f"/docs/packages/{name}.md"), lemons=items)


@pytest.fixture
def repo(tmp_path) -> Path:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "src").mkdir()
    return tmp_path / "src"


def test_each_condition(repo):
    docs = [
        _package("core", {}),
        _package("grove", {"brief": True}),
        _package("solo", {"brief": False}),
        _package("reviewer", {"brief-text": "^# Review "}),
        _package("python", {"file": "pyproject.toml"}),
        _package("elsewhere", {"cwd": "/somewhere/else/**"}),
        _package("here", {"cwd": f"{repo.parent}/**"}),
        _package("author", {"brief": True, "branch": "not-default"}),
    ]
    reviewer = lemons.Lemon(repo, "# Review app#3: a fix\n", on_default_branch=False)

    assert lemons.packages(docs, reviewer) == [
        "core",
        "grove",
        "reviewer",
        "python",
        "here",
        "author",
    ]


def test_not_and_alternatives(repo):
    docs = [
        _package("author", {"brief": True, "not": {"brief-text": "^# Review "}}),
        _package("either", {"cwd": "/nowhere/**"}, {"file": "pyproject.toml"}),
    ]

    assert lemons.packages(docs, lemons.Lemon(repo, "# Review app#3\n")) == ["either"]
    assert lemons.packages(docs, lemons.Lemon(repo, "# Fix the app\n")) == ["author", "either"]


def test_a_branch_condition_matches_nothing_when_the_branch_is_unknown(repo):
    docs = [_package("author", {"branch": "not-default"})]

    assert lemons.packages(docs, lemons.Lemon(repo, "", on_default_branch=None)) == []


def test_an_unknown_key_matches_no_lemon(repo):
    assert lemons.packages([_package("hq", {"role": "hq"})], lemons.Lemon(repo)) == []


def test_the_default_branch_check_runs_in_the_session_s_folder(tmp_path):
    (tmp_path / "ON_MAIN").touch()

    assert lemons.on_default_branch("test -e ON_MAIN", tmp_path) is True
    assert lemons.on_default_branch("test -e ON_MAIN", tmp_path.parent) is False
    assert lemons.on_default_branch("", tmp_path) is None


def test_group_and_under_match_a_lemon_s_groups_and_ancestors(repo):
    docs = [
        _package("oria", {"group": "oria"}),
        _package("lead", {"under": "MilkyWay"}),
        _package("hq", {"under": "HqDesk.control-center"}),
    ]
    lemon = lemons.Lemon(repo, groups=("oria",), ancestors=("MilkyWay.oria-lead",))

    assert lemons.packages(docs, lemon) == ["oria", "lead"]
    assert lemons.packages(docs, lemons.Lemon(repo)) == []


def test_scoped_only_takes_the_packages_for_a_group_or_a_lead(repo):
    docs = [_package("core", {}), _package("oria", {"group": "oria"})]

    assert lemons.packages(docs, lemons.Lemon(repo, groups=("oria",)), scoped_only=True) == ["oria"]


def test_kin_reads_groups_and_ancestors_from_the_database():
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "oria"), ["SweetShy.upload"])
        links.set_parent(conn, "SweetShy.upload", "MilkyWay.oria-lead")
        links.set_parent(conn, "MilkyWay.oria-lead", "HqDesk.control-center")

    assert lemons.kin("SweetShy.upload") == (
        ("oria",),
        ("MilkyWay.oria-lead", "HqDesk.control-center"),
    )
    assert lemons.kin("") == ((), ())
