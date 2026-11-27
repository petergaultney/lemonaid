"""The Relay plugin as lemonaid runs it: a process serving requests on stdin and stdout."""

import io
import subprocess
import sys

from lemonaid_relay_comments import cli, threads

_DOC = 'Intro {==the claim==}{{author="Sam">>is this\ntrue?<<}} and {{author="Mo (Author)">>noted<<}}\n'


def _request(operation: str, names: tuple[str, ...] = (), text: str = _DOC) -> bytes:
    body = text.encode()
    return (
        f"{operation} /doc.md\n".encode()
        + b"".join(f"name {n}\n".encode() for n in names)
        + f"text {len(body)}\n".encode()
        + body
    )


def _serve(*requests: bytes) -> bytes:
    out = io.BytesIO()
    cli.serve(io.BytesIO(b"".join(requests)), out)
    return out.getvalue()


def _answer(result: str) -> bytes:
    return f"ok {len(result.encode())}\n{result}".encode()


def test_it_says_hello_then_answers_each_request_in_turn():
    asked, answered = threads.threads(_DOC)

    assert _serve(_request("body"), _request("threads", ("Mo (Author)", "Mo"))) == (
        b"lemonaid-doc-plugin 1\n"
        + _answer("Intro the claim and \n")
        + _answer(
            f"thread {threads.key(asked)}\n"
            "last Sam\n"
            "waiting\n"
            "gist Sam: is this true?\n"
            "text Sam:\n"
            "text is this\n"
            "text true?\n"
            f"thread {threads.key(answered)}\n"
            "last Mo (Author)\n"
            "gist Mo (Author): noted\n"
            "text Mo (Author):\n"
            "text noted\n"
        )
    )


def test_an_unknown_operation_is_an_error_and_the_next_request_still_answers():
    served = _serve(_request("explain"), _request("body", text="plain"))

    assert served == b"lemonaid-doc-plugin 1\nerror unknown operation explain\n" + _answer("plain")


def test_the_installed_command_exits_when_stdin_closes():
    done = subprocess.run(
        [sys.executable, "-m", "lemonaid_relay_comments"],
        input=_request("body", text='a {{author="S">>x<<}} b'),
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert done.stdout == b"lemonaid-doc-plugin 1\n" + _answer("a  b")
