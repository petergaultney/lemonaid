import argparse

import pytest

from lemonaid.brief import check, lemon_table, lemons_cli, now_edit
from lemonaid.watch import subscriptions

_HEADER = "| Lemon | Purpose | Watch |\n|---|---|---|\n"


def test_add_set_and_remove_round_trip():
    text = lemon_table.add("# task\n", "other.WordyBin", "Reviewer of my PR", ["blocked", "done"])
    assert lemon_table.rows(text) == [
        lemon_table.Row("other.WordyBin", "Reviewer of my PR", ("blocked", "done"))
    ]
    assert check.structure(text) == []
    text = lemon_table.set_row(text, "other.WordyBin", "Reviews it", None)
    assert lemon_table.rows(text)[0].watch == ("blocked", "done")
    assert lemon_table.rows(text)[0].purpose == "Reviews it"
    text = lemon_table.set_row(text, "other.WordyBin", None, ["merge"])
    assert lemon_table.rows(text)[0].watch == ("merge",)
    text = lemon_table.remove(text, "other.WordyBin")
    assert "Lemons" not in [s.heading for s in now_edit.now_of(text).sections]


def test_an_empty_watch_cell_means_the_defaults():
    row = lemon_table.rows("# task\n\n## Now\n\n### Lemons\n\n" + _HEADER + "| a.B | why | |\n")[0]
    assert row.watch == () and row.wake == ("merge", "done", "needs")


def test_lemons_section_goes_after_docs_and_before_done(tmp_path):
    text = "# task\n\n## Now\n\n### Done\n\n- done\n\n## Watching\n"
    text = lemon_table.add(text, "a.B", "why")
    assert [s.heading for s in now_edit.now_of(text).sections] == ["Lemons", "Done"]
    assert check.structure(text) == []


@pytest.mark.parametrize(
    "rows, problem",
    [
        ("| a.B | why | sleeping |", "sleeping is not a status"),
        ("| a.B | why |", "invalid lemon row"),
        ("| a.B | why | done |\n| a.B | again | done |", "a.B has two rows"),
    ],
)
def test_brief_check_refuses_malformed_rows(rows, problem):
    text = f"# task\n\n## Now\n\n### Lemons\n\n{_HEADER}{rows}\n"
    assert any(problem in p for p in check.structure(text))


def test_edits_refuse_an_unparsed_table_without_losing_rows():
    text = "# task\n\n## Now\n\n### Lemons\n\n| Lemon | Purpose | Edits |\n|---|---|---|\n| a.B | x | y |\n"
    with pytest.raises(ValueError, match="Cannot rewrite ### Lemons"):
        lemon_table.add(text, "c.D", "new")


def test_removing_an_unlisted_lemon_is_an_error():
    with pytest.raises(ValueError, match="No row in ### Lemons"):
        lemon_table.remove("# task\n", "a.B")


def test_cli_takes_statuses_and_needs_only():
    parser = argparse.ArgumentParser()
    lemons_cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["lemon", "add", "--self", "a.B", "--to", "blocked", "--to", "needs"])
    assert args.to == ["blocked", "needs"]
    with pytest.raises(SystemExit):
        parser.parse_args(["lemon", "add", "--self", "a.B", "--to", "working"])


def test_report_hands_rows_to_the_briefs_subscription(tmp_path):
    text = lemon_table.add("# task\n\nParent: lead.WordyBin\n\n## Now\n", "a.B", "why", ["done"])
    reading = subscriptions.report(text, tmp_path, owner="me.WordyBin")
    (briefs,) = [s for s in reading.specs if s.kind == "briefs"]
    assert briefs.lemons == (lemon_table.Row("a.B", "why", ("done",)),)
    assert briefs.needs


def test_a_pipe_in_a_purpose_round_trips_through_every_edit():
    text = lemon_table.add("# task\n", "a.B", "x | y")
    for lemon in ("c.D", "e.F"):
        text = lemon_table.add(text, lemon, "z")
    assert lemon_table.rows(text)[0].purpose == "x | y"
    assert lemon_table.rows(lemon_table.set_row(text, "c.D", "q", None))[0].purpose == "x | y"
