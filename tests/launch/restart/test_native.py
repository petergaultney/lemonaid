import dataclasses

from lemonaid.launch.restart import native, process

from . import shared


def test_hook_records_only_matching_native_process_ownership(monkeypatch):
    monkeypatch.setattr(process, "ancestry", lambda *a: [shared.SOURCE, shared.ROOT])
    native.observe({"session_id": shared.SESSION}, "codex")
    assert native.binding(shared.CHANNEL) == {
        "session_id": shared.SESSION,
        "identity": dataclasses.asdict(shared.SOURCE),
    }
    native.observe({"session_id": shared.SESSION}, "claude")
    assert native.binding("claude:" + shared.SESSION[:8]) is None


def test_unavailable_process_inspection_does_not_break_normal_hooks(monkeypatch):
    def denied(*a):
        raise PermissionError("test sandbox")

    monkeypatch.setattr(process, "ancestry", denied)
    native.observe({"session_id": shared.SESSION}, "codex")
    assert native.binding(shared.CHANNEL) is None
