from lemonaid.config import _parse_config
from lemonaid.inbox import context_use
from lemonaid.inbox.context_use import Threshold


def test_thresholds_read_a_share_of_the_window_or_a_token_count(capsys):
    config = _parse_config(
        {
            "tui": {
                "context_threshold": {
                    "claude": "50%",
                    "codex": 200000,
                    "gpt-5.6-sol": "0.65M",
                    "gpt-5.6-luna": "650k",
                    "claude-haiku-5-5": "80%",
                    "bad": "lots",
                    "ambiguous": "50",
                    "worse": True,
                }
            }
        }
    )

    assert config.tui.context_threshold == {
        "claude": Threshold(share=0.5),
        "codex": Threshold(tokens=200000),
        "gpt-5.6-sol": Threshold(tokens=650_000),
        "gpt-5.6-luna": Threshold(tokens=650_000),
        "claude-haiku-5-5": Threshold(share=0.8),
    }
    assert "bad" in (err := capsys.readouterr().err)
    assert "ambiguous" in err


def test_a_model_threshold_wins_over_its_harness_and_unset_shows_nothing():
    thresholds = {"claude": Threshold(share=0.5), "claude-haiku-5-5": Threshold(tokens=1000)}

    assert context_use.threshold_for(thresholds, "claude", "claude-haiku-5-5") == Threshold(
        tokens=1000
    )
    assert context_use.threshold_for(thresholds, "claude", "claude-opus-5-5") == Threshold(
        share=0.5
    )
    assert context_use.threshold_for(thresholds, "codex", "gpt-5.6-sol") is None
    assert _parse_config({}).tui.context_threshold == {}


def test_percent_counts_against_the_threshold_not_the_window():
    assert context_use.percent(100_000, 200_000, Threshold(share=0.5)) == 100
    assert context_use.percent(50_000, 200_000, Threshold(share=0.5)) == 50
    assert context_use.percent(150_000, 0, Threshold(tokens=100_000)) == 150


def test_percent_is_none_without_a_window_to_share_or_with_a_zero_threshold():
    assert context_use.percent(50_000, 0, Threshold(share=0.5)) is None
    assert context_use.percent(50_000, 200_000, Threshold(tokens=0)) is None
    assert context_use.percent(0, 200_000, Threshold(share=0.5)) is None
