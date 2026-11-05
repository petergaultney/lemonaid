import pytest

from lemonaid import go
from lemonaid.brief import attached, identity, store
from lemonaid.cmux import navigation
from lemonaid.inbox import db

from .shared import run

SURFACE = navigation.Surface("W1", "WS1", "S1")


@pytest.fixture
def target():
    path = store.briefs_dir() / "jump.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Jump\n")
    with db.connect() as conn:
        db.add(
            conn,
            "claude:jump",
            "",
            switch_source="cmux",
            metadata={"tty": "/dev/ttys001", "cmux_surface": "S1", "session_id": "jump"},
        )
        attached.attach(conn, "claude:jump", path)
        return identity.ensure(conn, path)


@pytest.fixture
def located(monkeypatch):
    """Where locate_cmux says the lemon is; the test sets `located.answer`."""

    class Located:
        answer = SURFACE
        switched: list[navigation.Surface] = []

    def locate(metadata):
        assert metadata["cmux_surface"] == "S1"
        if isinstance(Located.answer, Exception):
            raise Located.answer
        return Located.answer

    monkeypatch.setattr(go.front_end.cmux, "locate", locate)
    monkeypatch.setattr(
        go.cmux.navigation,
        "switch_to_surface",
        lambda surface: Located.switched.append(surface) or True,
    )
    monkeypatch.setattr(go.cmux.recreate, "recreate", lambda *args: pytest.fail("recreated"))
    Located.switched = []
    return Located


@pytest.mark.parametrize("form", ["id", "channel", "url"])
def test_jump_focuses_the_surface(target, located, form):
    value = {"id": target, "channel": "claude:jump", "url": f"lemonaid://go/{target}"}[form]
    run(value)
    assert located.switched == [SURFACE]
    with db.connect() as conn:
        assert db.get_by_channel(conn, "claude:jump").status == "unread"


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (None, "no cmux surface"),
        (navigation.AMBIGUOUS, "Several cmux surfaces"),
        (navigation.UNKNOWN, "Could not tell"),
        (navigation.CmuxUnavailable(), "cmux did not answer"),
    ],
)
def test_no_surface_to_trust_never_switches_or_resumes(target, located, capsys, answer, message):
    located.answer = answer
    with pytest.raises(SystemExit, match="1"):
        run(target)
    assert not located.switched
    assert message in capsys.readouterr().err


def test_failed_focus_is_reported(target, located, monkeypatch, capsys):
    monkeypatch.setattr(go.cmux.navigation, "switch_to_surface", lambda surface: False)
    with pytest.raises(SystemExit, match="1"):
        run(target)
    assert "did not focus" in capsys.readouterr().err


def test_client_is_refused_for_cmux(target, located, capsys):
    with pytest.raises(SystemExit, match="1"):
        run(target, "--client", "/dev/ttys005")
    assert not located.switched
    assert "--client names a tmux client" in capsys.readouterr().err
