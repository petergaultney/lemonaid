"""Which lemons notify between two reads of the grove: those with news since they were last read."""

import dataclasses

from lemonaid.grove.web.push import events
from tests.grove import shared


def _news(before, after):
    return [
        e.lemon.channel
        for e in events.between({x.channel: x for x in before}, {x.channel: x for x in after})
    ]


def test_a_lemon_that_reports_while_read_notifies_and_staying_unread_doesnt():
    read = dataclasses.replace(shared.lemon("claude:ada"), updated=10.0)
    reported = dataclasses.replace(read, unread=True, updated=20.0)

    assert _news([read], [reported]) == ["claude:ada"]
    assert _news([reported], [reported]) == []


def test_a_lemon_marked_unread_by_hand_doesnt_notify():
    read = dataclasses.replace(shared.lemon("claude:ada"), updated=10.0)

    assert _news([read], [dataclasses.replace(read, unread=True)]) == []


def test_a_new_report_while_still_unread_notifies_again():
    first = dataclasses.replace(shared.lemon("claude:ada"), unread=True, updated=10.0)

    assert _news([first], [dataclasses.replace(first, updated=20.0)]) == ["claude:ada"]


def test_a_status_change_without_news_doesnt_notify():
    assert _news([shared.lemon("claude:ada")], [shared.lemon("claude:ada", status="blocked")]) == []


def test_an_alerting_lemon_is_urgent_and_a_tap_opens_its_page():
    lemon = dataclasses.replace(shared.lemon("claude:ada/1", status="alert"), unread=True)

    (event,) = events.between({}, {lemon.channel: lemon})

    assert event.urgent
    assert event.message("done")["url"] == "lemon?channel=claude%3Aada%2F1"
    assert event.message("done")["tag"] == "claude:ada/1"
    assert event.message("done")["body"] == "done"


def test_the_text_is_the_start_of_the_last_reply_on_one_line():
    entries = [
        {"role": "lemon", "text": "old news"},
        {"role": "user", "text": "and now?"},
        {"role": "lemon", "text": "The lights\n\nare off."},
        {"role": "lemon", "text": "  "},
    ]

    assert events.said(entries) == "The lights are off."
    assert events.said([{"role": "lemon", "text": "x" * 300}], limit=20) == "x" * 17 + "..."
    assert events.said([{"role": "user", "text": "hi"}]) == ""


def test_a_lemon_read_since_is_cleared_and_one_never_unread_isnt():
    read = shared.lemon("claude:ada")
    unread = dataclasses.replace(read, unread=True)

    def cleared(before, after):
        return [
            e.lemon.channel
            for e in events.read_between(
                {x.channel: x for x in before}, {x.channel: x for x in after}
            )
        ]

    assert cleared([unread], [read]) == ["claude:ada"]
    assert cleared([read], [read]) == []
    assert events.Event(read).clear() == {"clear": "claude:ada"}
