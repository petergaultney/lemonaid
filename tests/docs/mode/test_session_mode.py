import pytest

from lemonaid.docs import mode


@pytest.fixture
def packages_built(monkeypatch):
    monkeypatch.setattr(mode, "_BUILT", frozenset({"classic", "packages"}))


@pytest.mark.usefixtures("packages_built")
def test_the_launch_s_mode_is_kept_by_a_resume_without_it():
    assert mode.session_mode("codex", "t1", launched="packages", default="classic") == "packages"

    assert mode.session_mode("codex", "t1", launched="", default="classic") == "packages"


@pytest.mark.usefixtures("packages_built")
def test_a_resume_launched_with_a_mode_takes_it():
    mode.session_mode("claude", "s1", launched="packages", default="classic")

    assert mode.session_mode("claude", "s1", launched="classic", default="packages") == "classic"


@pytest.mark.usefixtures("packages_built")
def test_a_session_with_no_launch_mode_or_record_gets_the_default():
    assert mode.session_mode("claude", "s2", launched="", default="packages") == "packages"


@pytest.mark.usefixtures("packages_built")
def test_an_unknown_launch_mode_gets_the_default():
    assert mode.session_mode("claude", "s3", launched="lean", default="packages") == "packages"


def test_packages_falls_back_to_classic_until_it_is_built():
    assert mode.session_mode("claude", "s4", launched="packages", default="packages") == "classic"


def test_a_session_without_an_id_still_gets_a_mode():
    assert mode.session_mode("codex", "", launched="", default="classic") == "classic"
