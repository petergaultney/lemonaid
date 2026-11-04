import pytest

from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import brief_says, fact, snapshot, task

_DOC = "/vault/decisions.md"

_STILL = "2026-10-31T11:00:00Z"


def _blocked(needs: str, links: str = "", status: str = "blocked", *files: dict[str, str]):
    facts = [
        fact("lemon", "Work.alpha", "activity", "idle"),
        fact("lemon", "Work.alpha", "idle_since", "2026-10-31T11:50:00Z"),
        *brief_says(status=status, needs=needs),
        fact("brief", "Work.alpha", "needs_links", links),
        *files,
    ]
    [one] = corpus.inputs([corpus._snapshot(snapshot([task()], facts), 0)])
    return rules.evaluate(checker_input.read(one.text))


def _doc(headings: str = "Pick a name\nOther", modified: str = _STILL, exists: str = "true"):
    return [
        fact("file", _DOC, "exists", exists),
        fact("file", _DOC, "modified_at", modified, "known" if exists == "true" else "unavailable"),
        fact("file", _DOC, "headings", headings, "known" if exists == "true" else "unavailable"),
    ]


@pytest.mark.parametrize("status", ["blocked", "alert"])
def test_blocked_or_alert_with_no_needs_is_challenged(status):
    [challenge] = _blocked("", "", status)

    assert challenge[2] == "status-claim" and challenge[3] == f"{status} no-needs"
    assert "no `Needs`" in challenge[6]


@pytest.mark.parametrize(
    ("link", "doc", "said"),
    [
        (_DOC, _doc(exists="false"), "doesn't exist"),
        (f"{_DOC}#Pick a colour", _doc(), "has no heading 'Pick a colour'"),
    ],
)
def test_a_needs_link_to_a_missing_file_or_heading_is_challenged(link, doc, said):
    [challenge] = _blocked("[ask](x)", link, "blocked", *doc)

    assert challenge[2] == "status-claim" and said in challenge[6]


@pytest.mark.parametrize(
    ("link", "doc"),
    [
        (f"{_DOC}#Pick a name", _doc()),
        (f"{_DOC}#pick a name!", _doc()),  # an anchor drops punctuation and case
        (f"{_DOC}#whats-next", _doc("What's next?")),  # GitHub's anchor form
        (_DOC, _doc()),
        (f"{_DOC}#Gone", _doc(modified="2026-10-31T11:59:30Z")),  # still being edited
        (f"{_DOC}#Gone", []),  # nothing known about the file
        ("", []),  # a Needs that links no local file
    ],
)
def test_a_needs_that_resolves_or_isnt_known_stands(link, doc):
    found = _blocked("see [ask](x)", link, "blocked", *doc)

    assert not any(r[0] == "challenge" and r[2] == "status-claim" for r in found)


def test_a_status_that_asks_nothing_needs_no_needs():
    found = _blocked("", "", "running")

    assert not any(r[0] == "challenge" and r[2] == "status-claim" for r in found)
