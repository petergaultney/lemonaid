import pytest

from lemonaid.tasks.checker import protocol


def test_round_trips_every_escaped_character():
    value = "100%\tdone\r\nnext %0A"
    text = protocol.render([("context", "note", value)])

    assert protocol.parse(text, protocol.INPUT) == [("context", "note", value)]
    assert text.count("\n") == 2


@pytest.mark.parametrize(
    "text",
    [
        "",
        "protocol\t2\n",
        "protocol\t1\nnope\ta\tb\n",
        "protocol\t1\ncontext\tonly-two\n",
        "protocol\t1\ncontext\ta\t50%\n",
        "protocol\t1\ncontext\ta\t%41\n",
    ],
)
def test_rejects_malformed_input(text):
    with pytest.raises(protocol.ProtocolError):
        protocol.parse(text, protocol.INPUT)
