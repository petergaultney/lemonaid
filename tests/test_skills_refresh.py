"""Installed skills follow the packaged text across upgrades, checked when `lma` starts."""

import asyncio
import os
import shutil

import pytest

from lemonaid import log
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.skills import compose, install, refresh


@pytest.fixture
def dirs(tmp_path):
    packaged = tmp_path / "packaged"
    for name in ("watch-doc", "watch-pr"):
        (packaged / name).mkdir(parents=True)
        (packaged / name / "SKILL.md").write_text(f"---\nname: {name}\n---\nv1\n")
    return packaged, tmp_path / "user", tmp_path / "rendered"


def _install(packaged, user, rendered, name):
    install.write_rendered(rendered, name, compose.render(packaged, user, name, "claude").text)


def _upgrade(packaged, name, body):
    path = packaged / name / "SKILL.md"
    path.write_text(f"---\nname: {name}\n---\n{body}\n")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))


def _rendered(rendered, name):
    return (rendered / name / "SKILL.md").read_text()


def test_an_upgrade_rerenders_installed_skills_with_their_overlay(dirs):
    packaged, user, rendered = dirs
    (user / "watch-pr").mkdir(parents=True)
    (user / "watch-pr" / "overlay.md").write_text("## Mine\n")
    _install(packaged, user, rendered, "watch-pr")
    refresh.refresh_if_stale(packaged, user, rendered, "claude")

    _upgrade(packaged, "watch-pr", "v2")
    result = refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert _rendered(rendered, "watch-pr") == "---\nname: watch-pr\n---\nv2\n\n## Mine\n"
    assert refresh.notice(result) == (
        "Refreshed installed skills after a lemonaid upgrade: watch-pr"
    )


def test_a_current_stamp_skips_rendering(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-pr")
    refresh.refresh_if_stale(packaged, user, rendered, "claude")
    (user / "watch-pr").mkdir(parents=True)
    (user / "watch-pr" / "overlay.md").write_text("## Mine\n")

    result = refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert _rendered(rendered, "watch-pr").endswith("v1\n")
    assert refresh.notice(result) == ""


def test_a_skill_never_installed_stays_uninstalled(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-pr")
    (packaged / "new-skill").mkdir()
    (packaged / "new-skill" / "SKILL.md").write_text("---\nname: new-skill\n---\n")

    refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert sorted(p.name for p in rendered.iterdir()) == [".packaged-stamp", "watch-pr"]


def test_a_rendered_directory_lemonaid_did_not_create_is_left_alone(dirs):
    packaged, user, rendered = dirs
    (rendered / "watch-pr").mkdir(parents=True)
    (rendered / "watch-pr" / "SKILL.md").write_text("theirs\n")

    refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert _rendered(rendered, "watch-pr") == "theirs\n"


def test_a_failed_refresh_is_reported_until_it_succeeds(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-doc")
    _install(packaged, user, rendered, "watch-pr")
    (user / "watch-doc").mkdir(parents=True)
    (user / "watch-doc" / "overlay.md").write_text("---\nname: x\n---\n")

    _upgrade(packaged, "watch-doc", "v2")
    _upgrade(packaged, "watch-pr", "v2")
    first = refresh.refresh_if_stale(packaged, user, rendered, "claude")
    again = refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert _rendered(rendered, "watch-doc").endswith("v1\n")
    assert _rendered(rendered, "watch-pr").endswith("v2\n")
    assert first == refresh.Refreshed(["watch-pr"], ["watch-doc"])
    assert again == refresh.Refreshed([], ["watch-doc"])
    assert refresh.notice(again) == (
        f"Could not refresh watch-doc after a lemonaid upgrade (details in {log.LOG_PATH}); "
        "run `lemonaid skills install`"
    )


def test_text_that_is_not_utf8_is_a_failed_refresh_not_an_exception(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-doc")
    _install(packaged, user, rendered, "watch-pr")
    (user / "watch-doc").mkdir(parents=True)
    (user / "watch-doc" / "overlay.md").write_bytes(b"\xff\n")
    (rendered / ".packaged-stamp").write_bytes(b"\xff\n")

    _upgrade(packaged, "watch-pr", "v2")
    refresh.refresh_if_stale(packaged, user, rendered, "claude")

    assert _rendered(rendered, "watch-pr").endswith("v2\n")
    assert (rendered / ".packaged-stamp").read_bytes() == b"\xff\n"


def test_an_unreadable_packaged_dir_is_a_failed_refresh(dirs):
    packaged, user, rendered = dirs
    shutil.rmtree(packaged)

    assert refresh.refresh_if_stale(packaged, user, rendered, "claude") == refresh.Refreshed(
        [], ["skills"]
    )


def test_lma_refreshes_at_startup_and_says_so():
    for harness in ("claude", "codex"):
        install.write_rendered(install.default_rendered_dir(harness), "watch-pr", "stale\n")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            return [n.message for n in app._notifications]

    messages = asyncio.run(run())

    assert messages == ["Refreshed installed skills after a lemonaid upgrade: watch-pr"]
    for harness in ("claude", "codex"):
        assert (install.default_rendered_dir(harness) / "watch-pr" / "SKILL.md").read_text() == (
            compose.render(
                compose.PACKAGED_DIR, compose.default_user_dir(), "watch-pr", harness
            ).text
        )


def test_a_single_copy_install_is_migrated_to_per_harness_copies(tmp_path, monkeypatch):
    claude_skills = tmp_path / "claude-skills"
    monkeypatch.setenv("LEMONAID_CLAUDE_SKILLS_DIR", str(claude_skills))
    monkeypatch.setenv("LEMONAID_CODEX_SKILLS_DIR", str(tmp_path / "codex-skills"))
    old = install.rendered_root()
    install.write_rendered(old, "watch-pr", "old text\n")
    claude_skills.mkdir()
    (claude_skills / "watch-pr").symlink_to(old / "watch-pr")

    refresh.refresh_installed()

    assert not (old / "watch-pr").exists()
    assert (claude_skills / "watch-pr").resolve() == install.default_rendered_dir(
        "claude"
    ) / "watch-pr"
    assert "--codex-thread" not in (claude_skills / "watch-pr" / "SKILL.md").read_text()
    assert install.is_rendered(install.default_rendered_dir("codex"), "watch-pr")
