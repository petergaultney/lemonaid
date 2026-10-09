from rich.console import Console

from lemonaid.inbox.tui import backend_indicators, context_reading

_CONSOLE = Console(color_system="truecolor")


def test_default_backend_labels_name_the_provider_until_the_model_is_known():
    assert backend_indicators.backend_label("claude:session", {}) == "Anthropic"
    assert backend_indicators.backend_label("codex:session", {}) == "OpenAI"
    assert backend_indicators.backend_label("openclaw:session", {}) == "🦞"


def test_backend_glyphs_have_backend_specific_colours():
    claude = backend_indicators.backend_text("claude:session", {}, True)
    codex = backend_indicators.backend_text("codex:session", {}, False)

    assert claude.plain == "Anthropic"
    assert claude.spans[-1].style == "#d88760"
    assert codex.plain == "OpenAI"
    assert codex.spans[-1].style == "#c0c4c8"


def test_detected_models_replace_the_backend_fallback_with_family_and_version():
    opus = backend_indicators.backend_text(
        "claude:session", {"claude": "A"}, True, model="claude-opus-5-5"
    )
    sol = backend_indicators.backend_text(
        "codex:session", {"codex": "O"}, False, model="gpt-5.6-sol"
    )

    assert opus.plain == "Opus 5.5"
    assert opus.spans[-1].style == "#d88760"
    assert sol.plain == "Sol 5.6"
    assert sol.spans[-1].style == "#c0c4c8"
    assert opus.justify == "right"
    assert sol.justify == "right"


def test_a_dated_model_id_does_not_treat_the_date_as_a_minor_version():
    opus = backend_indicators.backend_text(
        "claude:session", {}, False, model="claude-opus-5-20260923"
    )

    assert opus.plain == "Opus 5"


def test_a_dashed_openai_version_keeps_its_order():
    sol = backend_indicators.backend_text("codex:session", {}, False, model="gpt-5-6-sol")

    assert sol.plain == "Sol 5.6"


def test_openclaw_can_show_an_underlying_model_provider():
    sonnet = backend_indicators.backend_text(
        "openclaw:session",
        {},
        False,
        model="claude-sonnet-4-6",
        model_provider="anthropic",
    )

    assert sonnet.plain == "Sonnet 4.6"
    assert sonnet.spans[-1].style == "#d88760"


def test_context_use_precedes_the_model_and_runs_purple_to_red_at_its_threshold():
    def reading(percent: int):
        cell = backend_indicators.backend_text(
            "claude:session", {}, False, model="claude-opus-5-5", context_percent=percent
        )
        return cell, cell.get_style_at_offset(_CONSOLE, 0).color.get_truecolor()

    low, purple = reading(0)
    _, blue = reading(15)
    _, middle = reading(50)
    _, red = reading(100)
    over, magenta = reading(200)

    assert low.plain == "0%  Opus 5.5"
    assert low.justify == "right"
    assert (purple.red, purple.green, purple.blue) == (75, 0, 130)
    assert (blue.red, blue.green, blue.blue) == (50, 130, 255)
    assert middle not in (blue, red)
    assert (red.red, red.green, red.blue) == (255, 60, 30)
    assert (magenta.red, magenta.green, magenta.blue) == (255, 0, 255)
    assert over.get_style_at_offset(_CONSOLE, len(over.plain) - 1).color.name == "#d88760"


def test_split_separates_the_reading_from_the_model_label():
    cell = backend_indicators.backend_text(
        "codex:session", {}, False, model="gpt-5.6-sol", context_percent=12
    )
    reading, model = context_reading.split(cell)

    assert (reading.plain, model.plain) == ("12%  ", "Sol 5.6")
    assert (
        context_reading.split(backend_indicators.backend_text("codex:s", {}, False))[0].plain == ""
    )
