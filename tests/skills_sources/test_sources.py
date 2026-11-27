"""Skill sources: finding their directories, and which source owns each skill name."""

import sys

from lemonaid.skills import compose, sources
from lemonaid.skills.source_config import Source, parse

from .shared import skill


def test_a_source_is_a_path_a_command_that_prints_one_or_a_fetch(tmp_path):
    for name in ("by-path", "printed", "fetched"):
        skill(tmp_path / name, f"{name}-skill")
    printer = f'{sys.executable} -c "print({str(tmp_path / "printed")!r})"'
    copy = f"cp -R {tmp_path / 'fetched'} {{dir}}"

    found = sources.locate(
        parse(
            {
                "sources": [
                    {"name": "a", "path": str(tmp_path / "by-path")},
                    {"name": "b", "command": printer},
                    {"name": "c", "fetch": copy},
                ]
            }
        )
    )

    assert [(s.name, s.dir) for s in found] == [
        (sources.PACKAGED, compose.PACKAGED_DIR),
        ("a", tmp_path / "by-path"),
        ("b", tmp_path / "printed"),
        ("c", sources.fetched_dir(Source("c"))),
    ]
    assert (sources.fetched_dir(Source("c")) / "fetched-skill" / "SKILL.md").is_file()


def test_a_fetched_source_is_fetched_once_and_updated_only_when_asked(tmp_path):
    log = tmp_path / "log"
    source = Source(
        "c",
        fetch=("sh", "-c", f'mkdir "$0" && echo fetch >> {log}', "{dir}"),
        update=("sh", "-c", f"echo update >> {log}", "{dir}"),
    )

    for update in (False, False, True):
        sources.locate([source], update)

    assert log.read_text().split() == ["fetch", "update"]


def test_an_earlier_source_keeps_a_name_and_optional_skills_install_only_when_named(
    tmp_path, capsys
):
    skill(tmp_path / "mine", "watch-doc")  # lemonaid's packaged skill has this name
    skill(tmp_path / "mine", "reply-format")
    skill(tmp_path / "mine", "review-guide")
    (tmp_path / "mine" / "skills.toml").write_text('optional = ["review-guide"]\n')

    owners = sources.catalog(sources.locate([Source("mine", path=str(tmp_path / "mine"))]))

    assert owners["watch-doc"].name == sources.PACKAGED
    assert owners["reply-format"].name == owners["review-guide"].name == "mine"
    assert "already has it" in capsys.readouterr().err
    assert "reply-format" in sources.default_names(owners)
    assert "review-guide" not in sources.default_names(owners)


def test_an_entry_needs_one_way_to_find_its_directory(capsys):
    assert parse(
        {
            "sources": [
                {"name": "two", "path": "/a", "command": "b"},
                {"name": "no-dir", "fetch": "git clone url"},
                {"name": "lemonaid", "path": "/a"},
                {"name": "ok", "fetch": "git clone url {dir}", "update": "git -C {dir} pull"},
            ]
        }
    ) == (
        Source("ok", fetch=("git", "clone", "url", "{dir}"), update=("git", "-C", "{dir}", "pull")),
    )
    assert capsys.readouterr().err.count("ignored") == 3


def test_a_fetch_that_fails_after_making_its_directory_is_tried_again(tmp_path):
    attempts = tmp_path / "attempts"
    fails_once = f'mkdir "$0" && echo x >> {attempts} && [ "$(wc -l < {attempts})" -gt 1 ]'
    source = Source("c", fetch=("sh", "-c", fails_once, "{dir}"))

    first = sources.locate([source])
    second = sources.locate([source])

    assert [s.name for s in first] == [sources.PACKAGED]
    assert [s.name for s in second] == [sources.PACKAGED, "c"]
    assert attempts.read_text().count("x") == 2
