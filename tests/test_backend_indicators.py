from lemonaid.inbox.tui import backend_indicators


def test_default_backend_labels_are_quiet_distinct_glyphs():
    assert backend_indicators.backend_label("claude:session", {}) == "A"
    assert backend_indicators.backend_label("codex:session", {}) == "O"
    assert backend_indicators.backend_label("openclaw:session", {}) == "🦞"


def test_backend_glyphs_have_backend_specific_colours():
    claude = backend_indicators.backend_text("claude:session", {}, True)
    codex = backend_indicators.backend_text("codex:session", {}, False)

    assert claude.plain == "A"
    assert claude.spans[-1].style == "#d88760"
    assert codex.plain == "O"
    assert codex.spans[-1].style == "#c0c4c8"


def test_detected_models_replace_the_backend_fallback_with_a_family_letter():
    opus = backend_indicators.backend_text(
        "claude:session", {"claude": "A"}, True, model="claude-opus-5-5"
    )
    sol = backend_indicators.backend_text(
        "codex:session", {"codex": "O"}, False, model="gpt-5.6-sol"
    )

    assert opus.plain == "O"
    assert opus.spans[-1].style == "#d88760"
    assert sol.plain == "S"
    assert sol.spans[-1].style == "#c0c4c8"


def test_openclaw_can_show_an_underlying_model_provider():
    sonnet = backend_indicators.backend_text(
        "openclaw:session",
        {},
        False,
        model="claude-sonnet-4-6",
        model_provider="anthropic",
    )

    assert sonnet.plain == "S"
    assert sonnet.spans[-1].style == "#d88760"
