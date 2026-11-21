"""The suite's tmux guard, protecting a private server that stands in for the developer's."""

import os
import shutil
import subprocess
import tempfile
import typing as ty
import uuid
from collections import abc

import pytest

from tests import tmux_guard

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="needs tmux")


class _World(ty.NamedTuple):
    guard: tmux_guard.Guard
    tmpdir: str  # the developer's TMUX_TMPDIR
    socket: str  # the developer's server, tmux's default under tmpdir
    link: str  # a symlink to socket


@pytest.fixture
def world(tmp_path) -> abc.Iterator[_World]:
    with tempfile.TemporaryDirectory(prefix="lma-tg-", dir="/tmp") as tmpdir:
        socket = os.path.realpath(f"{tmpdir}/tmux-{os.getuid()}/default")
        env = {k: v for k, v in os.environ.items() if k != "TMUX"} | {"TMUX_TMPDIR": tmpdir}
        subprocess.run(["tmux", "-f", "/dev/null", "new-session", "-d"], env=env, check=True)
        os.symlink(socket, f"{tmpdir}/link")
        guard = tmux_guard.install(
            tmp_path, shutil.which("tmux") or "", tmux_guard.guarded("", tmpdir)
        )
        assert guard is not None
        try:
            yield _World(guard, tmpdir, socket, f"{tmpdir}/link")
        finally:
            subprocess.run(["tmux", "-S", socket, "kill-server"], capture_output=True)


def _run(
    guard: tmux_guard.Guard, args: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_TMPDIR")}
    return subprocess.run(
        [str(guard.bin / "tmux"), *args], env=base | env, capture_output=True, text=True
    )


_REACHES = {
    "TMUX over TMUX_TMPDIR": lambda w: (
        ["kill-server"],
        {"TMUX": f"{w.socket},1,0", "TMUX_TMPDIR": "/"},
    ),
    "the default server": lambda w: (["kill-server"], {"TMUX_TMPDIR": w.tmpdir}),
    "-S": lambda w: (["-S", w.socket, "kill-server"], {}),
    "-S naming a link to it": lambda w: (["-S", w.link, "kill-server"], {}),
    "TMUX naming a link to it": lambda w: (["kill-server"], {"TMUX": f"{w.link},1,0"}),
    "-L under TMUX_TMPDIR": lambda w: (
        ["-uL", "default", "kill-server"],
        {"TMUX": "/nowhere,1,0", "TMUX_TMPDIR": w.tmpdir},
    ),
}


@pytest.mark.parametrize("reach", _REACHES.values(), ids=_REACHES.keys())
def test_a_command_bound_for_the_developers_server_is_refused_and_recorded(world, reach):
    args, env = reach(world)

    refused = _run(world.guard, args, env)

    assert refused.returncode == 1 and world.socket in refused.stderr
    assert tmux_guard.take(world.guard) == f"tmux {' '.join(args)} -> {world.socket}\n"
    assert subprocess.run(["tmux", "-S", world.socket, "has-session"]).returncode == 0


def test_a_command_for_another_server_reaches_it(world):
    other = f"{world.tmpdir}/other"
    try:
        started = _run(world.guard, ["-S", other, "-f", "/dev/null", "new-session", "-d"], {})
        found = _run(
            world.guard, ["display-message", "-p", "#{socket_path}"], {"TMUX": f"{other},1,0"}
        )
    finally:
        subprocess.run(["tmux", "-S", other, "kill-server"], capture_output=True)

    assert started.returncode == 0 and found.stdout.strip() == other
    assert tmux_guard.take(world.guard) == ""


def test_a_tmpdir_that_does_not_resolve_falls_back_to_tmp_as_tmux_does(tmp_path):
    label = f"lma-tg-{uuid.uuid4().hex[:8]}"
    socket = os.path.realpath(f"/tmp/tmux-{os.getuid()}/{label}")
    guard = tmux_guard.install(tmp_path, shutil.which("tmux") or "", [socket])
    assert guard is not None
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_TMPDIR")}
    subprocess.run(
        ["tmux", "-L", label, "-f", "/dev/null", "new-session", "-d"], env=env, check=True
    )
    try:
        refused = _run(guard, ["-L", label, "kill-server"], {"TMUX_TMPDIR": str(tmp_path / "no")})
        alive = subprocess.run(["tmux", "-S", socket, "has-session"]).returncode == 0
    finally:
        subprocess.run(["tmux", "-S", socket, "kill-server"], capture_output=True)

    assert refused.returncode == 1 and alive
    assert tmux_guard.take(guard) == f"tmux -L {label} kill-server -> {socket}\n"


def test_the_developers_servers_are_the_attached_one_and_the_defaults():
    assert tmux_guard.guarded("/private/tmp/tmux-7/work,12,3", "/private/var") == [
        "/private/tmp/tmux-7/work",
        f"/private/var/tmux-{os.getuid()}/default",
        os.path.realpath(f"/tmp/tmux-{os.getuid()}/default"),
    ]
