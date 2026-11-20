"""Grove tests stand on fixed roads and a fixed stream, not the ones a new grove gets, so changing
those defaults moves no test's ground. `test_landmarks` checks the defaults themselves, kept here
as `DEFAULT_ROADS` and `DEFAULT_STREAM`.
"""

import copy

from lemonaid.grove.layout import landmarks

DEFAULT_ROADS, DEFAULT_STREAM = landmarks.default_roads, landmarks.default_stream

# Two roads crossing at the middle of the world, and a stream wandering across it.
_ROADS = [
    [[0, 27], [52, 29], [105, 30], [157, 32], [210, 30]],
    [[99, 0], [103, 15], [105, 30], [108, 45], [106, 60]],
]
_STREAM = [
    [0, 24], [17, 29], [35, 28], [52, 24], [70, 24], [87, 30], [105, 34],
    [122, 32], [140, 29], [157, 30], [175, 36], [192, 39], [210, 36],
]  # fmt: skip

landmarks.default_roads = lambda: copy.deepcopy(_ROADS)
landmarks.default_stream = lambda: copy.deepcopy(_STREAM)
