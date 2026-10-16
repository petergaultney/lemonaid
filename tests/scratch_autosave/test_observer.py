import subprocess

import pytest

from lemonaid.tmux import follow, scratch, scratch_autosave
from tests.scratch_autosave.shared import settle, start


def test_resize_is_settled_once_and_updates_placeholders(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    tmux("select-window", "-t", "a:w1")
    observer.poll(1)
    tmux("resize-pane", "-t", pane, "-x", "65")
    observer.poll(2)
    tmux("resize-pane", "-t", pane, "-x", "70")
    observer.poll(2.5)
    observer.poll(3)
    assert scratch.saved_size("left") == "58"
    observer.poll(3.5)
    assert scratch.saved_size("left") == "70"
    assert tmux("show-option", "-gqv", follow.WIDTH_OPTION).stdout.strip() == "70"
    for slot in follow.placeholders("a:w2"):
        assert tmux("display", "-pt", slot, "#{pane_width}").stdout.strip() == "70"
    observer.poll(4)
    tmux("select-window", "-t", "a:w2")
    assert tmux("display", "-pt", pane, "#{pane_width}").stdout.strip() == "70"


@pytest.mark.parametrize("width", [200, 80, 245])
def test_client_resize_preserves_preference(tmux, monkeypatch, width):
    pane, observer = start(tmux, monkeypatch)
    tmux("refresh-client", "-C", f"{width}x90")
    settle(observer)
    assert scratch.saved_size("left") == "58"
    tmux("refresh-client", "-C", "245x90")
    settle(observer, 4)
    assert tmux("display", "-pt", pane, "#{pane_width}").stdout.strip() == "58"


def test_zoom_unzoom_between_samples_cancels_pending_save(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    tmux("resize-pane", "-t", pane, "-x", "70")
    observer.poll(1)
    tmux("resize-pane", "-t", pane, "-Z")
    tmux("resize-pane", "-t", pane, "-Z")
    settle(observer, 2)
    assert scratch.saved_size("left") == "58"


def test_zoom_is_never_saved(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    tmux("resize-pane", "-t", pane, "-Z")
    settle(observer)
    tmux("resize-pane", "-t", pane, "-Z")
    settle(observer, 4)
    assert scratch.saved_size("left") == "58"


@pytest.mark.parametrize("transition", ["follow", "layout", "park", "off", "flip"])
def test_transition_cancels_pending_size(tmux, monkeypatch, transition):
    pane, observer = start(tmux, monkeypatch)
    tmux("resize-pane", "-t", pane, "-x", "70")
    observer.poll(1)
    if transition == "follow":
        tmux("select-window", "-t", "a:w1")
    elif transition == "layout":
        tmux("select-layout", "-t", "a:w2", "even-horizontal")
    elif transition == "park":
        scratch._clear_state()
        scratch._hide(pane)
    elif transition == "off":
        scratch.set_follow_enabled(False)
    else:
        scratch.move_scratch("12", "top")
    settle(observer, 3)
    assert scratch.saved_size("left") == "58"
    assert scratch.saved_size("top") == "12"


def test_startup_drift_is_only_a_baseline(tmux, monkeypatch):
    pane, _ = start(tmux, monkeypatch)
    tmux("resize-pane", "-t", pane, "-x", "70")
    observer = scratch_autosave.Observer()
    settle(observer)
    assert scratch.saved_size("left") == "58"
    tmux("resize-pane", "-t", pane, "-x", "72")
    settle(observer, 3)
    assert scratch.saved_size("left") == "72"


def test_ordinary_inbox_cannot_save_the_managed_pane(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    monkeypatch.setenv("TMUX_PANE", tmux("display", "-pt", "a:w1", "#{pane_id}").stdout.strip())
    tmux("resize-pane", "-t", pane, "-x", "70")
    settle(observer)
    assert scratch.saved_size("left") == "58"


def test_adjacent_key_resize_changes_scratch_axis(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    main = tmux("display", "-pt", "a:w2", "#{pane_id}").stdout.strip()
    tmux("resize-pane", "-t", main, "-L", "5")
    settle(observer)
    assert scratch.saved_size("left") == "53"


def test_top_size_and_both_axes_survive_server_restart(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    tmux("resize-pane", "-t", pane, "-x", "70")
    settle(observer)
    scratch.move_scratch("12", "top")
    observer.poll(3)
    assert scratch_autosave._sample(pane) is not None
    tmux("resize-pane", "-t", pane, "-y", "16")
    settle(observer, 4)
    assert scratch.saved_size("top") == "16"
    tmux("kill-server")
    assert tmux("-f", "/dev/null", "new-session", "-d", "-s", "restarted").returncode == 0
    scratch._publish_all("10", "top")
    assert tmux("show-option", "-gqv", follow.WIDTH_OPTION).stdout.strip() == "70"
    assert tmux("show-option", "-gqv", follow.HEIGHT_OPTION).stdout.strip() == "16"


def test_multiple_client_fitting_does_not_save(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    socket = tmux("display", "-p", "#{socket_path}").stdout.strip()
    client = subprocess.Popen(
        ["tmux", "-S", socket, "-C", "attach", "-t", "a"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tmux("refresh-client", "-C", "80x30")
        settle(observer)
        assert scratch.saved_size("left") == "58"
    finally:
        client.kill()
        client.wait()


def test_work_pane_border_on_other_axis_does_not_save(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    main = tmux("display", "-pt", "a:w2", "#{pane_id}").stdout.strip()
    tmux("split-window", "-t", main, "-v")
    observer.poll(1)
    tmux("resize-pane", "-t", main, "-y", "25")
    settle(observer, 2)
    assert scratch.saved_size("left") == "58"
    assert scratch.saved_size("top") == "12"


def test_top_client_shrink_and_grow_preserves_height(tmux, monkeypatch):
    pane, observer = start(tmux, monkeypatch)
    scratch.move_scratch("12", "top")
    observer.poll(1)
    tmux("refresh-client", "-C", "245x20")
    settle(observer, 2)
    assert scratch.saved_size("top") == "12"
    tmux("refresh-client", "-C", "245x90")
    settle(observer, 5)
    assert scratch.saved_size("top") == "12"
    assert tmux("display", "-pt", pane, "#{pane_height}").stdout.strip() == "12"


@pytest.mark.parametrize("layout_command", ["next-layout", "previous-layout"])
@pytest.mark.parametrize("pending", [False, True])
def test_layout_cycle_counts_as_external_geometry(tmux, monkeypatch, layout_command, pending):
    pane, observer = start(tmux, monkeypatch)
    if pending:
        tmux("resize-pane", "-t", pane, "-x", "70")
        observer.poll(1)
    assert tmux(layout_command, "-t", "a:w2").returncode == 0
    size = tmux("display", "-pt", pane, "#{pane_width}").stdout.strip()
    settle(observer, 2)
    assert scratch.saved_size("left") == size
    assert tmux("show-option", "-gqv", follow.WIDTH_OPTION).stdout.strip() == size


@pytest.mark.parametrize("direction", ["-n", "-p"])
@pytest.mark.parametrize("pending", [False, True])
def test_select_layout_cycle_preserves_preference(tmux, monkeypatch, direction, pending):
    pane, observer = start(tmux, monkeypatch)
    if pending:
        tmux("resize-pane", "-t", pane, "-x", "70")
        observer.poll(1)
    assert tmux("select-layout", direction, "-t", "a:w2").returncode == 0
    settle(observer, 2)
    assert scratch.saved_size("left") == "58"
    assert tmux("show-option", "-gqv", follow.WIDTH_OPTION).stdout.strip() == "58"
