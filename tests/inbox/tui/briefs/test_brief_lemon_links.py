"""A Lemon-ID lemonaid knows is a link to `lemonaid://go/<Lemon-ID>`; anything else stays text."""

from lemonaid.brief import links, render
from lemonaid.inbox.tui.briefs import brief_identity

_KNOWN = frozenset({"fix-widget.OzoneYes", "old-name.RobotOne"})


def _section(**fields) -> render.Section:
    return render.Section(
        title="Fix it",
        lemon=None,
        state="",
        raw_status="",
        prs=(),
        path=None,
        mtime=0.0,
        body="",
        lemon_id="fix-widget.OzoneYes",
        **fields,
    )


def _hrefs(text) -> list[tuple[str, str]]:
    return [
        (text.plain[s.start : s.end], s.style.link)
        for s in text.spans
        if getattr(s.style, "link", None)
    ]


def test_the_header_links_the_brief_id_and_the_parent():
    shown = brief_identity.lines(_section(parent="lead.LogicFun", compact=True), 80)

    assert [(plain, url) for line in shown for plain, url in _hrefs(line)] == [
        ("fix-widget.OzoneYes", "lemonaid://go/fix-widget.OzoneYes"),
        ("lead.LogicFun", "lemonaid://go/lead.LogicFun"),
    ]


def test_a_wrapped_header_id_keeps_its_link_on_every_line():
    shown = brief_identity.lines(_section(), 10)

    assert {url for line in shown for _, url in _hrefs(line)} == {
        "lemonaid://go/fix-widget.OzoneYes"
    }


def test_a_table_row_links_a_known_id_in_a_cell():
    table = "| Child | Status |\n| --- | --- |\n| fix-widget.OzoneYes | done |\n| `old-name.RobotOne` | x |"

    assert links.linkify(table, (), _KNOWN) == (
        "| Child | Status |\n| --- | --- |\n"
        "| [fix-widget.OzoneYes](<lemonaid://go/fix-widget.OzoneYes>) | done |\n"
        "| [`old-name.RobotOne`](<lemonaid://go/old-name.RobotOne>) | x |"
    )


def test_prose_links_a_known_id_and_keeps_the_sentence_period():
    assert links.linkify("- Waiting on fix-widget.OzoneYes.", (), _KNOWN) == (
        "- Waiting on [fix-widget.OzoneYes](<lemonaid://go/fix-widget.OzoneYes>)."
    )


def test_text_that_is_not_a_known_id_stays_plain():
    source = "see other.Unknown, notes.md and v1.2.3 or `x.y` in `fix-widget.OzoneYes.bak`"

    assert links.linkify(source, (), _KNOWN) == source


def test_without_known_ids_nothing_links():
    assert links.linkify("fix-widget.OzoneYes", ()) == "fix-widget.OzoneYes"
