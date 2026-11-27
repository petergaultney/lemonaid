"""Sending one lemon's news to every device."""

import dataclasses

from lemonaid.grove.web.push import events, pusher, webpush
from tests.grove import shared


def test_a_device_that_cant_be_sent_to_doesnt_keep_the_next_from_its_news(monkeypatch):
    sent = []

    def send(to, message, pem, urgent=False, topic=""):
        if to.endpoint.endswith("bad"):
            raise ValueError("not a P-256 point")
        sent.append(to.endpoint)

    monkeypatch.setattr(webpush, "send", send)
    monkeypatch.setattr(pusher.devices, "key", lambda: b"pem")
    monkeypatch.setattr(pusher, "_said", lambda channel: "done")
    bad = webpush.Subscription("https://push.example/bad", "pub", "sec")
    good = webpush.Subscription("https://push.example/good", "pub", "sec")

    pusher._deliver(events.Event(shared.lemon("claude:ada")), [bad, good])

    assert sent == ["https://push.example/good"]


def _pusher(monkeypatch, devices):
    """A Pusher whose sending threads wait in the returned list until the test runs them."""
    sent, waiting = [], []

    class _Later:
        def __init__(self, target, args, daemon):
            self.start = lambda: waiting.append(lambda: target(*args))

    monkeypatch.setattr(pusher.threading, "Thread", _Later)
    monkeypatch.setattr(pusher, "_lemons", lambda grove: grove)
    monkeypatch.setattr(webpush, "available", lambda: True)
    monkeypatch.setattr(webpush, "send", lambda to, message, *a, **k: sent.append((to, message)))
    monkeypatch.setattr(pusher.devices, "key", lambda: b"pem")
    monkeypatch.setattr(pusher.devices, "all_devices", lambda: list(devices))
    monkeypatch.setattr(pusher, "_said", lambda channel: "done")
    return pusher.Pusher(), sent, waiting


def _run(waiting):
    while waiting:
        waiting.pop(0)()


def _device(name):
    return webpush.Subscription(f"https://push.example/{name}", "pub", "sec")


_READ = shared.lemon("claude:ada")
_UNREAD = dataclasses.replace(_READ, unread=True)


def _grove(lemon):
    return {lemon.channel: lemon}


def _sent(sent):
    return [(to.endpoint, "clear" in message) for to, message in sent]


def test_a_lemon_read_elsewhere_is_cleared_only_from_the_devices_shown_its_news(monkeypatch):
    devices = [_device("ada")]
    p, sent, waiting = _pusher(monkeypatch, devices)

    p.saw(_grove(_READ))
    p.saw(_grove(_UNREAD))
    _run(waiting)
    devices.append(_device("grace"))  # turned on after the news went out
    p.saw(_grove(_READ))
    _run(waiting)

    assert _sent(sent) == [("https://push.example/ada", False), ("https://push.example/ada", True)]


def test_a_lemon_read_while_its_news_is_still_being_sent_is_cleared_once_it_has_gone(monkeypatch):
    p, sent, waiting = _pusher(monkeypatch, [_device("ada")])

    p.saw(_grove(_READ))
    p.saw(_grove(_UNREAD))
    p.saw(_grove(_READ))  # before the news is sent
    _run(waiting)
    p.saw(_grove(_READ))
    _run(waiting)

    assert _sent(sent) == [("https://push.example/ada", False), ("https://push.example/ada", True)]


def test_safari_isnt_sent_clears_as_it_revokes_a_push_that_shows_nothing(monkeypatch):
    safari = webpush.Subscription("https://web.push.apple.com/ada", "pub", "sec")
    p, sent, waiting = _pusher(monkeypatch, [safari])

    p.saw(_grove(_READ))
    p.saw(_grove(_UNREAD))
    _run(waiting)
    p.saw(_grove(_READ))
    _run(waiting)

    assert _sent(sent) == [("https://web.push.apple.com/ada", False)]
