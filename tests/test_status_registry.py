from lemonaid import config, status_registry
from lemonaid.brief import status_guide
from lemonaid.inbox import order


def test_the_defaults_are_todays_words_most_urgent_first():
    assert status_registry.names(status_registry.parse([])) == (
        "alert",
        "blocked",
        "running",
        "merge",
        "approve",
        "review",
        "done",
    )


def test_an_entry_changes_a_default_or_adds_a_word_in_rank_order(capsys):
    found = status_registry.parse(
        [
            {"name": "review", "attention": True},
            {"name": "vendor", "color": "#8d6e63", "glyph": "v", "rank": 65, "description": "x"},
        ]
    )
    by_name = status_registry.by_name(found)

    assert status_registry.names(found)[-3:] == ("review", "vendor", "done")
    assert by_name["review"].attention and by_name["review"].fill == "#8a5a2b"
    assert (by_name["vendor"].fill, by_name["vendor"].text, by_name["vendor"].glyph) == (
        "#8d6e63",
        "#8d6e63",
        "v",
    )
    assert capsys.readouterr().err == ""


def test_done_and_unusable_entries_are_skipped_with_a_warning(capsys):
    found = status_registry.parse(
        [
            {"name": "done", "color": "#000000"},
            {"name": "nocolor"},
            {"name": "waiting", "color": "#111111"},
            {"name": "review", "rank": "first"},
            "not a table",
        ]
    )

    assert found == status_registry.DEFAULTS
    assert capsys.readouterr().err.count("Warning") == 5


def test_attention_and_yours_are_separate_sets():
    defaults = status_registry.DEFAULTS

    assert status_registry.attention(defaults) == {
        "alert",
        "blocked",
        "running",
        "merge",
        "approve",
    }
    assert status_registry.yours(defaults) == {"alert", "blocked", "merge", "approve"}


def test_a_configured_word_gets_its_own_inbox_band_and_help_entry(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[[brief.statuses]]\nname = "vendor"\ncolor = "#8d6e63"\nrank = 65\n'
        'description = "an outside party owes a reply"\n'
    )
    configured = config.brief_statuses()

    assert order.band_names()[:7] == (
        "alert",
        "blocked",
        "running",
        "merge",
        "approve",
        "review",
        "vendor",
    )
    assert order.special_status("vendor")
    assert "vendor   an outside party owes a reply" in status_guide.guide(configured)


def test_a_name_may_have_hyphens_but_a_color_must_be_hex(capsys):
    found = status_registry.parse(
        [
            {"name": "waiting-on-vendor", "color": "#8d6e63"},
            {"name": "typo", "color": "#notrgb"},
            {"name": "review", "on_fill": "white"},
        ]
    )

    assert "waiting-on-vendor" in status_registry.names(found)
    assert "typo" not in status_registry.names(found)
    assert status_registry.by_name(found)["review"].on_fill == "#ffffff"
    assert capsys.readouterr().err.count("must be a color") == 2
