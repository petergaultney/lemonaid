from lemonaid.usage import samples

WINDOW_S = 1000 * 60  # a 1000-minute window; epoch 0 is its start when resets_at == WINDOW_S
MID = WINDOW_S / 2


def sample(used: float, resets_at: float = WINDOW_S) -> samples.Sample:
    return samples.Sample(used, int(resets_at), 1000)
