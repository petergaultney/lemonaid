"""Supervise a handoff from a shell that owns a suspended harness job."""

import os
import signal
import subprocess
import sys
import time
from contextlib import suppress

from ..inbox import db, self_session
from . import attached, handoff_coordinator, handoff_state


def channel_on_tty(conn, tty: str) -> str:
    """Resolve one attached live lemon recorded on the controlling TTY."""
    holders = {item.channel for item in attached.everything(conn) if item.channel}
    matches = {
        row.channel
        for row in self_session._live_newest_rows(conn)
        if row.channel in holders and row.metadata.get("tty") == tty
    }
    if len(matches) != 1:
        raise LookupError(
            f"Expected one attached live lemon on {tty}; found {len(matches)}. "
            "Refusing to guess which session to hand off."
        )
    return matches.pop()


def harnesses_on_tty(conn, tty: str) -> set[str]:
    """Return harness names for attached live sessions recorded on *tty*."""
    holders = {item.channel for item in attached.everything(conn) if item.channel}
    return {
        row.channel.split(":", 1)[0]
        for row in self_session._live_newest_rows(conn)
        if row.channel in holders and row.metadata.get("tty") == tty
    }


def stopped_harness_on_tty(
    tty: str, harnesses: set[str]
) -> tuple[str, tuple[int, int, str, str]] | None:
    """Find the one stopped attached-harness process group on *tty*, if present."""
    tty_name = tty.removeprefix("/dev/")
    try:
        result = subprocess.run(
            [
                "ps",
                "-t",
                tty_name,
                "-o",
                "pid=",
                "-o",
                "pgid=",
                "-o",
                "stat=",
                "-o",
                "lstart=",
                "-o",
                "comm=",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"Could not inspect stopped jobs on {tty}") from error
    if result.returncode and result.stderr.strip():
        raise ValueError(f"Could not inspect stopped jobs on {tty}: {result.stderr.strip()}")

    matches: list[tuple[str, int, int, str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 8)
        if len(fields) != 9:
            continue
        try:
            pid, pgid = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        process_tty_stat = fields[2]
        started = " ".join(fields[3:8])
        executable = fields[8]
        executable_name = os.path.basename(executable).lower()
        matching_harnesses = [
            name for name in harnesses if executable_name.startswith(name.lower())
        ]
        if "T" in process_tty_stat and matching_harnesses and pgid != os.getpgrp():
            harness = max(matching_harnesses, key=len)
            matches.append((harness, pid, pgid, started, executable))

    groups = {item[2] for item in matches}
    if not groups:
        return None
    if len(groups) != 1:
        raise ValueError(
            f"Found {len(groups)} stopped harness process groups on {tty}; "
            "refusing to guess which one to hand off."
        )

    pgid = groups.pop()
    # The group is unambiguous even if its harness has helper processes. Prefer
    # its leader so the PID/start-time check guards the group signal.
    harness, pid, _, started, _ = min(matches, key=lambda item: (item[1] != pgid, item[1]))
    checked_pgid, checked_tty, checked_start = stopped_job(pid, tty, harness)
    if checked_pgid != pgid:
        raise ValueError("The stopped harness changed process groups while being inspected")
    return harness, (pid, checked_pgid, checked_tty, checked_start)


def stopped_job_on_tty(tty: str, harness: str) -> tuple[int, int, str, str]:
    """Find the requested stopped harness process group on *tty*."""
    stopped = stopped_harness_on_tty(tty, {harness})
    if stopped is None:
        raise ValueError(
            f"No stopped {harness} process found on {tty}; press Ctrl-Z in the outgoing "
            "harness, then run this command from that terminal."
        )
    stopped_harness, job = stopped
    if stopped_harness != harness:
        raise ValueError(
            f"Found stopped {stopped_harness} on {tty}, but the attached session is {harness}; "
            "refusing to guess which one to hand off."
        )
    return job


def _report(token: str) -> dict:
    with db.connect() as conn:
        return handoff_coordinator.advance(conn, token)


def _job_process(pid: int) -> tuple[int, str, str, str, str] | None:
    try:
        result = subprocess.run(
            [
                "ps",
                "-p",
                str(pid),
                "-o",
                "pgid=",
                "-o",
                "tty=",
                "-o",
                "stat=",
                "-o",
                "lstart=",
                "-o",
                "comm=",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if (
        result.returncode
        or not (fields := result.stdout.strip().split(None, 8))
        or len(fields) != 9
    ):
        return None
    return int(fields[0]), fields[1], fields[2], " ".join(fields[3:8]), fields[8]


def stopped_job(pid: int, tty: str, harness: str) -> tuple[int, str, str]:
    """Validate the stopped shell job before trusting it as the source harness."""
    process = _job_process(pid)
    if process is None:
        raise ValueError("The suspended harness process is unavailable")
    pgid, process_tty, stat, started, executable = process
    if process_tty != tty.removeprefix("/dev/") or "T" not in stat or pgid == os.getpgrp():
        raise ValueError("The selected shell job is not a stopped process on this terminal")
    if harness not in os.path.basename(executable).lower():
        raise ValueError("The selected shell job is not the outgoing harness")
    return pgid, process_tty, started


def stop_job_if_same(pid: int, pgid: int, tty: str, started: str, force: bool = False) -> bool:
    """End only the job whose process identity was checked at request time."""
    process = _job_process(pid)
    if process is None or (process[0], process[1], process[3]) != (pgid, tty, started):
        return False
    if pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        return False
    return True


def _check_terminal(token: str, tty: str) -> str:
    with db.connect() as conn:
        row = handoff_state.get(conn, token)
        source = db.get_by_channel(conn, row["source"], unread_only=False)
        if source is None or source.metadata.get("tty") != tty:
            raise ValueError("The outgoing harness was recorded on another terminal")
        return row["source"]


def _run(command: str) -> int:
    """Run configured POSIX command lines without depending on the caller's shell."""
    return subprocess.run(["/bin/sh", "-c", command], check=False).returncode


def _foreground(fd: int, pgid: int) -> None:
    """Give a process group the controlling terminal, even when this CLI is backgrounded."""
    previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    try:
        os.tcsetpgrp(fd, pgid)
    finally:
        signal.signal(signal.SIGTTOU, previous)


def _same_job(pid: int, pgid: int, tty: str, started: str) -> bool:
    process = _job_process(pid)
    return process is not None and (process[0], process[1], process[3]) == (pgid, tty, started)


def process_group_on_tty(pgid: int, tty: str) -> bool | None:
    """Whether any non-zombie process in *pgid* still owns *tty*."""
    try:
        result = subprocess.run(
            ["ps", "-t", tty.removeprefix("/dev/"), "-o", "pgid=", "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode and result.stderr.strip():
        # macOS ps exits non-zero and prints this when the source has exited
        # and no processes remain attached to the terminal.
        if "no processes found" in result.stderr.lower() and not result.stdout.strip():
            return False
        return None
    found_group = False
    parsed_rows = 0
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            process_pgid = int(fields[0])
        except ValueError:
            continue
        parsed_rows += 1
        if process_pgid == pgid:
            found_group = True
            if not fields[1].startswith("Z"):
                return True
    if found_group or parsed_rows or not result.stdout.strip():
        return False
    return None


def launch_from_tty(token: str, source_job: tuple[int, int, str, str]) -> None:
    """Resume one verified stopped source, then run the replacement in this terminal."""
    if not sys.stdin.isatty():
        raise ValueError("Same-terminal handoff needs the outgoing terminal")
    fd = sys.stdin.fileno()
    tty = os.ttyname(fd)
    channel = _check_terminal(token, tty)
    pid, pgid, source_tty, started = source_job
    if source_tty != tty.removeprefix("/dev/"):
        raise ValueError("The stopped harness was identified on another terminal")

    own_pgid = os.getpgrp()
    try:
        foreground = os.tcgetpgrp(fd)
    except OSError as error:
        raise ValueError(f"Could not inspect foreground process group on {tty}") from error
    if foreground != own_pgid:
        raise ValueError("Run the handoff command directly from the foreground shell")
    if not _same_job(pid, pgid, source_tty, started) or stopped_job(
        pid, tty, channel.split(":", 1)[0]
    ) != (pgid, source_tty, started):
        raise ValueError("The stopped harness changed before terminal handoff")

    source_was_resumed = False
    with db.connect() as conn:
        deadline = handoff_state.get(conn, token)["deadline"]
    source_running: bool | None = True
    try:
        _foreground(fd, pgid)
        if not _same_job(pid, pgid, source_tty, started) or stopped_job(
            pid, tty, channel.split(":", 1)[0]
        ) != (pgid, source_tty, started):
            raise ValueError("The stopped harness changed while acquiring the terminal")
        os.killpg(pgid, signal.SIGCONT)
        source_was_resumed = True

        while True:
            report = _report(token)
            if report["phase"] in ("failed", "complete"):
                break

            source_running = process_group_on_tty(pgid, tty)
            if source_running is None:
                raise ValueError(f"Could not check whether the outgoing harness left {tty}")
            if report["phase"] == "launched" and not source_running:
                break
            if report["phase"] != "launched" and not source_running:
                # The harness exits immediately after writing its marker. Give
                # the stability check a moment to observe the completed file.
                for _ in range(5):
                    if report.get("missing") != ["brief file is still changing"]:
                        break
                    time.sleep(0.1)
                    report = _report(token)
                    if report["phase"] == "launched":
                        break
                if report["phase"] == "launched":
                    break
                with db.connect() as conn:
                    handoff_coordinator.recover_source(
                        conn,
                        handoff_state.get(conn, token),
                        "outgoing harness exited before readiness",
                    )
                report = _report(token)
                break
            if time.time() > deadline:
                break
            time.sleep(0.5)

        # The outgoing group may still be alive after an error or timeout. Stop
        # only the same process identity so the shell can safely regain control.
        source_running = process_group_on_tty(pgid, tty)
        if source_running:
            try:
                os.killpg(pgid, signal.SIGSTOP)
            except ProcessLookupError:
                source_running = False
        _foreground(fd, own_pgid)

        if report["phase"] == "complete":
            return
        if report["phase"] != "launched":
            print(
                "\n".join(report.get("missing") or ["Handoff did not reach readiness"]),
                file=sys.stderr,
            )
            if source_running is False and (resume := report.get("resume_command")):
                _run(resume)
            return

        command = report.get("start_command")
        if not command:
            raise ValueError("The destination harness has no start command")
        if process_group_on_tty(pgid, tty) is not False:
            raise ValueError("The outgoing harness may still be running on this terminal")

        print("Starting the replacement harness in this terminal.", file=sys.stderr)
        result = _run(command)
        report = _report(token)
        if report["phase"] == "complete":
            if result:
                raise SystemExit(result)
            return

        with db.connect() as conn:
            handoff_coordinator.recover_source(
                conn, handoff_state.get(conn, token), "target exited before accepting the brief"
            )
        report = _report(token)
        print("The replacement exited before accepting the brief.", file=sys.stderr)
        if resume := report.get("resume_command"):
            print("Resuming the outgoing harness in this terminal.", file=sys.stderr)
            _run(resume)
        else:
            raise ValueError("The outgoing session has no resume command")
    finally:
        # SIGTTOU must be ignored while reclaiming the terminal; the shell then
        # takes it back when this foreground command exits.
        try:
            if source_was_resumed and process_group_on_tty(pgid, tty):
                with suppress(ProcessLookupError):
                    os.killpg(pgid, signal.SIGSTOP)
        except OSError:
            pass
        try:
            if os.tcgetpgrp(fd) != own_pgid:
                _foreground(fd, own_pgid)
        except OSError:
            pass
