import json
import sys

import pytest

from lemonaid import cli
from lemonaid.brief import identity
from lemonaid.inbox import db
from tests.lineage.shared import lemon


def _run(monkeypatch, capsys, *args: str) -> dict | list:
    monkeypatch.setattr(sys, "argv", ["lemonaid", "grove", *args, "--json"])
    cli.main()
    return json.loads(capsys.readouterr().out)


def test_a_lemon_grafted_by_name_is_listed_until_its_channel_ungrafts_it(monkeypatch, capsys):
    stove, silly = lemon("stove", "claude:stove"), lemon("silly", "claude:silly")
    done = _run(
        monkeypatch,
        capsys,
        "graft",
        identity.brief_name(stove),
        "--onto",
        identity.brief_name(silly),
    )
    assert done == {"lemon": stove, "onto": silly, "waiting": False, "error": None}
    assert [(g["lemon"], g["onto"]) for g in _run(monkeypatch, capsys, "grafts")] == [
        (stove, silly)
    ]

    assert _run(monkeypatch, capsys, "ungraft", "claude:stove")["ungrafted"] is True
    assert _run(monkeypatch, capsys, "grafts") == []


def test_a_lemon_without_a_brief_is_grafted_by_channel_and_a_gone_host_waits(monkeypatch, capsys):
    gone = lemon("gone")
    with db.connect() as conn:
        db.add(conn, "claude:plain", "", metadata={})
    done = _run(monkeypatch, capsys, "graft", "claude:plain", "--onto", gone)
    assert (done["lemon"], done["onto"], done["waiting"]) == ("claude:plain", gone, True)


def test_a_loop_or_an_unknown_lemon_is_refused(monkeypatch, capsys):
    one, two = lemon("one", "claude:one"), lemon("two", "claude:two")
    _run(monkeypatch, capsys, "graft", one, "--onto", two)
    with pytest.raises(SystemExit):
        _run(monkeypatch, capsys, "graft", two, "--onto", one)
    assert "ungraft it first" in json.loads(capsys.readouterr().out)["error"]
    with pytest.raises(SystemExit):
        _run(monkeypatch, capsys, "graft", "NoSuchLemon", "--onto", one)
    assert json.loads(capsys.readouterr().out)["error"]
