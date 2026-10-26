"""What the grove draws: blocks (groups) of trees (places) that lemons hang on."""

import dataclasses


@dataclasses.dataclass(frozen=True)
class Lemon:
    channel: str
    notification_id: int
    name: str
    brief_id: str  # the WordyBin half of the Lemon-ID, or "" without a brief
    status: str  # the brief's Status word, or ""
    working: bool  # mid-turn
    quiet: bool  # read, between turns, no status: drawn dimmed
    model: str
    context: str  # "42%", or "" when not configured
    emoji: str
    pinned: bool
    born: float  # when lemonaid first saw it, epoch seconds
    session: str  # the terminal container it runs in, for display only
    window: str  # its window in that container, "" when it has none
    hidden: bool  # its brief says `Hidden: yes`, as a reviewer's does
    named: bool = False  # its name was given, in the inbox or by `inbox rename`, not derived
    unread: bool = False  # it has news the inbox marks unread


@dataclasses.dataclass(frozen=True)
class Tree:
    key: str  # what makes lemons share a tree: their place, else their terminal container
    label: str
    lemons: tuple[Lemon, ...]  # its main lemon first: see `source.blocks.main_first`
    lead: bool  # holds the group's lead

    @property
    def born(self) -> float:
        return min(lemon.born for lemon in self.lemons)


@dataclasses.dataclass(frozen=True)
class Block:
    name: str  # the group's name; "" for lemons in no group
    digit: str  # its place in the inbox's group order; "0" for no group
    color: str
    trees: tuple[Tree, ...]


@dataclasses.dataclass(frozen=True)
class Plot:
    """A block's ground in grove coordinates, which stays put once given."""

    x: int
    y: int
    w: int
    h: int
    roundness: float  # superellipse exponent: 2 is an ellipse, 8 nearly a rectangle
    seed: int  # wobbles the outline
    texture: str  # "rows", "diag", "wave", "dots"


@dataclasses.dataclass(frozen=True)
class Spot:
    """Where a tree stands, relative to its plot's corner."""

    x: int
    y: int
    letter: str


WORLD_WIDTH = 210
WORLD_HEIGHT = 60
