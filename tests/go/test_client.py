import pytest

from lemonaid import go


@pytest.mark.parametrize(
    "clients,explicit,source,expected",
    [
        ("/dev/a|here\n/dev/b|elsewhere", "", "%1", "/dev/a"),
        ("/dev/a|here\n/dev/b|here", "/dev/b", "", "/dev/b"),
        ("/dev/a|here\n/dev/b|here", "", "", None),
        ("", "", "", None),
        ("/dev/a|here", "/dev/missing", "", None),
    ],
)
def test_client_selection(monkeypatch, clients, explicit, source, expected):
    monkeypatch.setattr(
        go, "_tmux", lambda command, *args: clients if args[0] == "list-clients" else "%1|here"
    )
    if expected is None:
        with pytest.raises(LookupError):
            go._client(["tmux"], explicit, source)
    else:
        assert go._client(["tmux"], explicit, source) == expected
