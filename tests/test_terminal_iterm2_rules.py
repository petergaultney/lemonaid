"""Lemonaid's iTerm2 Smart Selection rule is replaced in place and never duplicated."""

import plistlib

from lemonaid.terminal import iterm2_rules

_MINE = {"notes": "mine", "regex": "x"}
_BUILT_IN = [{"notes": "Paths", "regex": "y"}]


def _install(profiles, regex="r"):
    return list(
        iterm2_rules.changed(profiles, iterm2_rules.rule(regex, "/bin/lemon aid"), _BUILT_IN)
    )


def test_installing_twice_changes_nothing_the_second_time():
    first = _install([{"Name": "A", "Smart Selection Rules": [_MINE]}])
    second = _install([profile for profile, _ in first])

    assert [verb for _, verb in first] == ["added"]
    assert [verb for _, verb in second] == ["unchanged"]
    assert second[0][0]["Smart Selection Rules"][0] == _MINE
    assert len(second[0][0]["Smart Selection Rules"]) == 2


def test_a_new_regex_replaces_lemonaids_rule_only():
    installed = [
        profile for profile, _ in _install([{"Name": "A", "Smart Selection Rules": [_MINE]}])
    ]
    [(profile, verb)] = _install(installed, regex="s")

    assert verb == "updated"
    assert [rule["regex"] for rule in profile["Smart Selection Rules"]] == ["x", "s"]


def test_a_profile_on_built_in_rules_gets_them_copied_in():
    [(profile, verb)] = _install([{"Name": "A"}])

    assert verb == "added"
    assert profile["Smart Selection Rules"][0] == _BUILT_IN[0]


def test_removing_leaves_the_users_rules():
    installed = [
        profile
        for profile, _ in _install([{"Name": "A", "Smart Selection Rules": [_MINE]}, {"Name": "B"}])
    ]
    removed = list(iterm2_rules.changed(installed, None, _BUILT_IN))

    assert [verb for _, verb in removed] == ["removed", "removed"]
    assert removed[0][0]["Smart Selection Rules"] == [_MINE]


def test_the_command_quotes_lemonaid_and_leaves_the_match_to_iterm2():
    [action] = iterm2_rules.rule("r", "/bin/lemon aid")["actions"]

    assert action["parameter"] == "'/bin/lemon aid' terminal open-vault \\0"


def test_saving_to_a_plist_keeps_its_other_settings(tmp_path):
    plist = tmp_path / "prefs.plist"
    plist.write_bytes(plistlib.dumps({"Other": 1, "New Bookmarks": []}))

    iterm2_rules.save(
        {iterm2_rules.PROFILES: [{"Name": "A"}], iterm2_rules.PRIORITIZE: True}, plist
    )

    assert iterm2_rules.load(plist) == {
        "Other": 1,
        "New Bookmarks": [{"Name": "A"}],
        "PrioritizeSmartSelectionActions": True,
    }
