from pathlib import Path

from lemonaid.docs import mode
from lemonaid.docs_config import DocsConfig

_ROOTED = DocsConfig(mode="classic", roots=(Path("/docs"),))
_PACKAGES = DocsConfig(mode="packages", roots=(Path("/docs"),))


def test_the_launch_s_mode_is_kept_by_a_resume_without_it():
    assert mode.session_mode("codex", "t1", launched="packages", config=_ROOTED) == "packages"

    assert mode.session_mode("codex", "t1", launched="", config=_ROOTED) == "packages"


def test_a_recorded_mode_outlasts_the_launch_variable():
    mode.session_mode("claude", "s1", launched="packages", config=_ROOTED)
    mode.record("claude", "s1", "classic")

    assert mode.session_mode("claude", "s1", launched="packages", config=_PACKAGES) == "classic"


def test_a_session_with_no_launch_mode_or_record_gets_the_default():
    assert mode.session_mode("claude", "s2", launched="", config=_PACKAGES) == "packages"


def test_an_unknown_launch_mode_gets_the_default():
    assert mode.session_mode("claude", "s3", launched="lean", config=_PACKAGES) == "packages"


def test_packages_without_roots_falls_back_to_classic_and_comes_back_with_them():
    assert mode.session_mode("claude", "s4", launched="packages", config=DocsConfig()) == "classic"

    assert mode.session_mode("claude", "s4", launched="", config=_ROOTED) == "packages"


def test_a_session_without_an_id_still_gets_a_mode():
    assert mode.session_mode("codex", "", launched="", config=_ROOTED) == "classic"
