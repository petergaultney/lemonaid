"""What the notifications page asks the server (`settings.html`): its key, and turning this device on,
off, or sending it a test."""

from . import devices, webpush


def key() -> dict:
    if not webpush.available():
        return {"problem": webpush.MISSING}

    return {"key": webpush.public_key(devices.key())}


def device(endpoint: str) -> bool:
    return devices.find(endpoint) is not None


def subscribe(subscription: dict) -> str:
    if not webpush.available():
        return webpush.MISSING

    devices.add(subscription)
    return "on"


def unsubscribe(endpoint: str) -> str:
    return "off" if devices.remove(endpoint) else "this device wasn't on"


def test(endpoint: str) -> str:
    found = devices.find(endpoint)
    if found is None:
        return "this device isn't on"

    try:
        webpush.send(
            found,
            {
                "title": "lemonaid",
                "body": "Notifications work on this device.",
                "tag": "test",
                "url": "groups",
            },
            devices.key(),
        )
    except webpush.Gone:
        devices.remove(endpoint)
        return "the browser dropped this device's subscription; turn it on again"

    except OSError as error:
        return f"couldn't send: {error}"

    return "sent"
