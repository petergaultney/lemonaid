from lemonaid.inbox.tui import backend_indicators


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
