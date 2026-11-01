"""Run a checker over a corpus offline and report each task's verdict, and which ones changed."""

import subprocess
import sys
import tempfile
import typing as ty
from collections import abc
from pathlib import Path

from . import corpus, protocol

DEFAULT_CHECKER = (sys.executable, "-m", "lemonaid.tasks.checker.default")

# Strongest first: a set with any challenge is a challenge, whatever else it holds.
_RANK = ("challenge", "adjudicate", "unknown", "wait", "ok")


class Verdict(ty.NamedTuple):
    snapshot: str
    task_id: str
    verdict: str
    records: list[protocol.Record]
    expected: str


def check_findings(task_id: str, records: abc.Sequence[protocol.Record]) -> None:
    """Raise ProtocolError unless *records* are a usable complete finding set for *task_id*."""
    if strangers := {r[1] for r in records} - {task_id}:
        raise protocol.ProtocolError(f"findings for other tasks: {', '.join(sorted(strangers))}")

    kinds = {r[0] for r in records}
    if "ok" in kinds and kinds & {"challenge", "adjudicate"}:
        raise protocol.ProtocolError("ok mixed with challenge or adjudicate")

    if not kinds - {"recheck"}:
        raise protocol.ProtocolError("no finding, only rechecks")


def _summary(records: abc.Sequence[protocol.Record]) -> str:
    kinds = {r[0] for r in records}
    return next(kind for kind in _RANK if kind in kinds)


def run_checker(
    argv: abc.Sequence[str], text: str, timeout: float, operation: str = "evaluate"
) -> str:
    """The checker's stdout for one input; raises CalledProcessError or TimeoutExpired."""
    with tempfile.NamedTemporaryFile("w", suffix=".tsv") as handle:
        handle.write(text)
        handle.flush()
        return subprocess.run(
            [*argv, operation, "--input", handle.name],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        ).stdout


def _verdict(argv: abc.Sequence[str], one: corpus.Input, expected: str, timeout: float) -> Verdict:
    try:
        records = protocol.parse(run_checker(argv, one.text, timeout), protocol.EVALUATE)
        check_findings(one.task_id, records)
    except (protocol.ProtocolError, subprocess.SubprocessError, OSError) as e:
        return Verdict(
            one.snapshot, one.task_id, "failure", [("failure", one.task_id, str(e))], expected
        )

    return Verdict(one.snapshot, one.task_id, _summary(records), records, expected)


def replay(
    argv: abc.Sequence[str], snapshots: abc.Sequence[corpus.Snapshot], timeout: float
) -> abc.Iterator[Verdict]:
    expected = {(s.name, task): verdict for s in snapshots for task, verdict in s.expected.items()}
    for one in corpus.inputs(snapshots):
        yield _verdict(argv, one, expected.get((one.snapshot, one.task_id), ""), timeout)


def changed(
    verdicts: abc.Iterable[Verdict], baseline: ty.Mapping[str, str]
) -> abc.Iterator[tuple[Verdict, str]]:
    """Each verdict differing from its expectation or from *baseline* (keyed `snapshot/task`),
    with what it was compared against."""
    for v in verdicts:
        before = baseline.get(f"{v.snapshot}/{v.task_id}", "")
        if v.expected and v.verdict != v.expected:
            yield v, f"expected {v.expected}"
        elif before and v.verdict != before:
            yield v, f"was {before}"


def load_baseline(path: Path) -> dict[str, str]:
    """`snapshot/task<TAB>verdict` lines, as written by `write_baseline`."""
    return dict(ln.split("\t", 1) for ln in path.read_text().splitlines() if ln.count("\t") == 1)


def write_baseline(path: Path, verdicts: abc.Iterable[Verdict]) -> None:
    path.write_text("".join(f"{v.snapshot}/{v.task_id}\t{v.verdict}\n" for v in verdicts))
