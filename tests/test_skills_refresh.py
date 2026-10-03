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
    install.write_rendered(rendered, name, compose.render(packaged, user, name).text)


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
    refresh.refresh_if_stale(packaged, user, rendered)

    _upgrade(packaged, "watch-pr", "v2")
    result = refresh.refresh_if_stale(packaged, user, rendered)

    assert _rendered(rendered, "watch-pr") == "---\nname: watch-pr\n---\nv2\n\n## Mine\n"
    assert refresh.notice(result) == (
        "Refreshed installed skills after a lemonaid upgrade: watch-pr"
    )


def test_a_current_stamp_skips_rendering(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-pr")
    refresh.refresh_if_stale(packaged, user, rendered)
    (user / "watch-pr").mkdir(parents=True)
    (user / "watch-pr" / "overlay.md").write_text("## Mine\n")

    result = refresh.refresh_if_stale(packaged, user, rendered)

    assert _rendered(rendered, "watch-pr").endswith("v1\n")
    assert refresh.notice(result) == ""


def test_a_skill_never_installed_stays_uninstalled(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-pr")
    (packaged / "new-skill").mkdir()
    (packaged / "new-skill" / "SKILL.md").write_text("---\nname: new-skill\n---\n")

    refresh.refresh_if_stale(packaged, user, rendered)

    assert sorted(p.name for p in rendered.iterdir()) == [".packaged-stamp", "watch-pr"]


def test_a_rendered_directory_lemonaid_did_not_create_is_left_alone(dirs):
    packaged, user, rendered = dirs
    (rendered / "watch-pr").mkdir(parents=True)
    (rendered / "watch-pr" / "SKILL.md").write_text("theirs\n")

    refresh.refresh_if_stale(packaged, user, rendered)

    assert _rendered(rendered, "watch-pr") == "theirs\n"


def test_a_failed_refresh_is_reported_until_it_succeeds(dirs):
    packaged, user, rendered = dirs
    _install(packaged, user, rendered, "watch-doc")
    _install(packaged, user, rendered, "watch-pr")
    (user / "watch-doc").mkdir(parents=True)
    (user / "watch-doc" / "overlay.md").write_text("---\nname: x\n---\n")

    _upgrade(packaged, "watch-doc", "v2")
    _upgrade(packaged, "watch-pr", "v2")
    first = refresh.refresh_if_stale(packaged, user, rendered)
    again = refresh.refresh_if_stale(packaged, user, rendered)

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
    refresh.refresh_if_stale(packaged, user, rendered)

    assert _rendered(rendered, "watch-pr").endswith("v2\n")
    assert (rendered / ".packaged-stamp").read_bytes() == b"\xff\n"


def test_an_unreadable_packaged_dir_is_a_failed_refresh(dirs):
    packaged, user, rendered = dirs
    shutil.rmtree(packaged)

    assert refresh.refresh_if_stale(packaged, user, rendered) == refresh.Refreshed([], ["skills"])


def test_lma_refreshes_at_startup_and_says_so():
    install.write_rendered(install.default_rendered_dir(), "watch-pr", "stale\n")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            return [n.message for n in app._notifications]

    messages = asyncio.run(run())

    assert messages == ["Refreshed installed skills after a lemonaid upgrade: watch-pr"]
    assert (install.default_rendered_dir() / "watch-pr" / "SKILL.md").read_text() == (
        compose.PACKAGED_DIR / "watch-pr" / "SKILL.md"
    ).read_text()
