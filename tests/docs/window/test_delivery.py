from lemonaid.docs import window


def _state() -> dict:
    return {"window": 1, "calls": 0, "delivered": {}, "shadowed": {}, "prompt": {}, "mode": ""}


def _match(state: dict, key: str = "a.md#", mtime: float = 1.0, **kwargs) -> str:
    return window.delivery(
        state, key, mtime, kwargs.get("reminder", True), "a.md#", kwargs.get("before", False)
    )


def test_a_section_is_given_in_full_once_per_window():
    state = _state()

    assert _match(state) == "full"
    window.given(state, "a.md#", 1.0, package=False)
    state["calls"] += window.REMIND_AFTER - 1
    assert _match(state) == ""


def test_a_repeat_match_gives_the_reminder_after_enough_calls():
    state = _state()
    window.given(state, "a.md#", 1.0, package=False)
    state["calls"] += window.REMIND_AFTER

    assert _match(state) == "reminder"
    assert _match(state, reminder=False) == ""


def test_a_doc_a_package_carried_gives_its_reminder_at_the_first_match():
    state = _state()
    window.given(state, "a.md#", 1.0, package=True)
    state["calls"] += 3

    assert _match(state, "a.md#Drafts") == "reminder"
    window.given(state, "a.md#Drafts", 1.0, package=False)
    assert _match(state, "a.md#Drafts") == ""


def test_a_before_trigger_refuses_once_even_after_a_package():
    state = _state()
    window.given(state, "a.md#", 1.0, package=True)

    assert _match(state, before=True) == "refuse"
    window.given(state, "a.md#", 1.0, package=False)
    assert _match(state, before=True) == ""


def test_a_changed_doc_is_given_in_full_again():
    state = _state()
    window.given(state, "a.md#", 1.0, package=False)

    assert _match(state, mtime=2.0) == "full"


def test_a_resume_keeps_the_window_and_compaction_starts_a_new_one():
    state = _state()
    window.given(state, "a.md#", 1.0, package=False)

    state["packages"], state["mode"] = ["core"], "packages"

    assert window.begin(state, "resume", "packages", ["core", "grove"]) is False
    assert state["delivered"] and state["packages"] == ["core"]
    assert window.begin(state, "compact", "packages", ["core", "grove"]) is True
    assert state == {
        "window": 2,
        "calls": 0,
        "delivered": {},
        "shadowed": {},
        "packages": ["core", "grove"],
        "prompt": {},
        "mode": "packages",
    }


def test_a_resume_in_another_mode_starts_a_new_window():
    state = {**_state(), "mode": "packages"}
    window.given(state, "a.md#", 1.0, package=False)

    assert window.begin(state, "resume", "classic", ["oria"]) is True
    assert (state["window"], state["mode"], state["delivered"]) == (2, "classic", {})


def test_a_new_window_still_holds_the_docs_in_the_system_prompt():
    state = {**_state(), "prompt": {"core.md#": 1.0}}

    window.begin(state, "compact", "packages", ["core"])

    assert _match(state, "core.md#") == "reminder"
    assert _match(state, "core.md#", mtime=2.0) == "full"
