import os
from pathlib import Path

from lemonaid.config import load_config


def test_the_cover_share_defaults_to_a_tenth_and_stays_between_none_and_all():
    assert load_config().tui.grove_window_cover_share == 0.1

    for written, read in (("0.25", 0.25), ("3", 1.0), ("-1", 0.0)):
        Path(os.environ["LEMONAID_CONFIG"]).write_text(
            f"[tui]\ngrove_window_cover_share = {written}\n"
        )
        assert load_config().tui.grove_window_cover_share == read
