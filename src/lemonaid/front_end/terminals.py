"""Which terminal a recorded lemon runs in, for code that only looks at terminals."""

from . import cmux, interface, tmux, wezterm


def all_terminals() -> tuple[interface.Terminal, ...]:
    """In the order a caller is placed: a tmux session run inside cmux or WezTerm is tmux's."""
    return (tmux.terminal(), wezterm.terminal(), cmux.terminal())


def named(name: str | None) -> interface.Terminal | None:
    """The terminal an inbox row's `switch_source` names, or None for one lemonaid doesn't know."""
    return next((each for each in all_terminals() if each.name == name), None)
