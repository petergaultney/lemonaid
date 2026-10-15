import pytest

from lemonaid import launch_config


@pytest.mark.parametrize(
    "entry",
    [
        {"windows": []},
        {"windows": [""], "lemon_window": -1},
        {"windows": [""], "lemon_window": 1},
        {"windows": [""], "lemon_window": True},
        {"windows": [42]},
        {"windows": "editor"},
        [],
    ],
)
def test_invalid_shapes_fail_before_launch(entry):
    with pytest.raises(ValueError, match=r"tmux-session\.shapes\.bad"):
        launch_config.parse_shapes({"bad": entry})
