import io

import pytest

from lemonaid.tasks.checker import protocol, stream


def test_frames_carry_any_records_and_failures_in_any_order():
    text = protocol.render([("watch", "lemon", "Work.alpha")])
    wire = (
        stream.response("2", text)
        + stream.failed("1", "bad\tinput")
        + stream.request("3", "describe", text)
    )

    found = list(stream.frames(io.StringIO(wire)))

    assert found == [
        stream.Frame("response", "2", "", text),
        stream.Frame("failed", "1", "bad\tinput", ""),
        stream.Frame("request", "3", "describe", text),
    ]


@pytest.mark.parametrize("wire", ["stray\n", stream.request("1", "describe", "protocol\t1\n")[:-6]])
def test_a_line_outside_a_frame_or_an_unended_frame_is_a_protocol_error(wire):
    with pytest.raises(protocol.ProtocolError):
        list(stream.frames(io.StringIO(wire)))


def test_serve_answers_each_request_and_fails_the_ones_it_cant():
    def respond(operation: str, text: str) -> str:
        if operation != "describe":
            raise ValueError(f"unknown operation {operation!r}")

        return text

    out = io.StringIO()
    stream.serve(
        respond,
        io.StringIO(
            stream.request("a", "describe", "protocol\t1\n") + stream.request("b", "x", "")
        ),
        out,
    )

    assert out.getvalue() == stream.response("a", "protocol\t1\n") + stream.failed(
        "b", "unknown operation 'x'"
    )
