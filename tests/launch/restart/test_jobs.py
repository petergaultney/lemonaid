import dataclasses

import pytest

from lemonaid.launch.restart import jobs, process

from . import shared


def test_codex_allows_only_its_direct_bundled_host_not_the_hosts_tool_job(monkeypatch):
    source = dataclasses.replace(shared.SOURCE, executable="/vendor/codex/codex")
    helper = dataclasses.replace(
        shared.SOURCE, pid=102, parent=source.pid, executable="/vendor/bin/codex-code-mode-host"
    )
    tool = dataclasses.replace(helper, pid=103, parent=helper.pid, executable="/bin/sleep")
    monkeypatch.setattr(jobs.launch_args, "argv", lambda pid: ["/vendor/bin/codex-code-mode-host"])
    monkeypatch.setattr(
        jobs.launch_args, "executable", lambda pid: "/vendor/bin/codex-code-mode-host"
    )
    assert jobs.helpers(source, "codex", [helper, tool]) == [helper]
    assert (
        jobs.helpers(
            source,
            "codex",
            [dataclasses.replace(helper, executable="/elsewhere/codex-code-mode-host")],
        )
        == []
    )


@pytest.mark.parametrize(
    "argv",
    [["caffeinate", "-i", "-t", "300"], ["caffeinate", "-i"], ["caffeinate", "-i", "-t", "999"]],
)
def test_claude_inhibitor_requires_exact_native_arguments_and_direct_parent(monkeypatch, argv):
    helper = dataclasses.replace(
        shared.SOURCE, pid=102, parent=shared.SOURCE.pid, executable="caffeinate"
    )
    monkeypatch.setattr(jobs.launch_args, "argv", lambda pid: argv)
    monkeypatch.setattr(jobs.launch_args, "executable", lambda pid: "/usr/bin/caffeinate")
    expected = [helper] if argv == ["caffeinate", "-i", "-t", "300"] else []
    assert jobs.helpers(shared.SOURCE, "claude", [helper]) == expected
    assert jobs.helpers(shared.SOURCE, "claude", [dataclasses.replace(helper, parent=999)]) == []
    assert (
        jobs.helpers(shared.SOURCE, "claude", [helper, dataclasses.replace(helper, pid=103)]) == []
    )


def test_reused_or_disappeared_helper_aborts_final_preflight(monkeypatch, tmp_path):
    plan = shared.plan(tmp_path)
    plan["helpers"] = [dataclasses.asdict(shared.SOURCE)]
    monkeypatch.setattr(process, "same", lambda identity: False)
    with pytest.raises(ValueError, match="helper generation changed"):
        jobs.saved(plan)


def test_spoofed_helper_argv_does_not_establish_native_ownership(monkeypatch):
    child = dataclasses.replace(
        shared.SOURCE, pid=102, parent=shared.SOURCE.pid, executable="caffeinate"
    )
    monkeypatch.setattr(jobs.launch_args, "argv", lambda pid: ["caffeinate", "-i", "-t", "300"])
    monkeypatch.setattr(jobs.launch_args, "executable", lambda pid: "/foreign/caffeinate")
    assert jobs.helpers(shared.SOURCE, "claude", [child]) == []
