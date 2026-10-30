"""A removal of an old registration never deletes the replacement written while it runs."""

import threading

from lemonaid.watch import scout_roster

_LEMON = "task.IndexElf"


def test_a_replacement_written_during_a_removal_survives(monkeypatch):
    old = scout_roster.register(_LEMON, "claude:00000000", "", "/work")
    replacement: list[scout_roster.Registration] = []
    writer = threading.Thread(
        target=lambda: replacement.append(
            scout_roster.register(_LEMON, "claude:abcd1234", "", "/work")
        )
    )
    read = scout_roster.read

    def read_then_replace(lemon_id):
        found = read(lemon_id)
        if not writer.is_alive() and not replacement:
            writer.start()  # the new session registers between the token check and the unlink
            writer.join(0.2)
        return found

    monkeypatch.setattr(scout_roster, "read", read_then_replace)

    scout_roster.remove(_LEMON, old.token)

    writer.join(5)
    monkeypatch.setattr(scout_roster, "read", read)
    assert replacement and scout_roster.read(_LEMON) == replacement[0]
