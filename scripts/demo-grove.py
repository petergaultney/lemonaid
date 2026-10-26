#!/usr/bin/env python3
"""Stage a grove of invented lemons on a throwaway tmux server, for screenshots.

    uv run scripts/demo-grove.py                 # the whole grove
    uv run scripts/demo-grove.py --keys 3        # zoomed into block 3
    uv run scripts/demo-screenshot.py docs/images/grove.png --columns 232 --rows 62

The grove needs 1.1 columns per grove unit to show whole (the grove is 210 units wide), so
the overview wants a terminal of at least 232 columns by 62 rows; any smaller and it pans.

Like `demo-inbox.py`, everything it touches is its own: the inbox, config, state and briefs
live under one scratch directory, and the tmux server has its own socket. Block plots and
tree spots are written into the demo's layout afterwards, so the picture is the same every
time rather than whatever the automatic layout chose. `--kill` tears it all down.
"""

import argparse
import copy
import importlib.util
import shutil
import subprocess
import sys
import time
import typing as ty
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("demo_inbox", HERE / "demo-inbox.py")
assert _spec and _spec.loader
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)  # points every LEMONAID_* variable at the demo's scratch directory

from lemonaid.brief import attached, identity  # noqa: E402
from lemonaid.groups import store as groups  # noqa: E402
from lemonaid.grove.layout import state  # noqa: E402
from lemonaid.inbox import db  # noqa: E402
from lemonaid.lineage import links  # noqa: E402


class Lemon(ty.NamedTuple):
    name: str  # the Brief-ID's name half
    task: str  # its description half
    status: str  # a brief status; "" for none
    parent: str  # the parent's task; "" for none
    backend: str
    model: str


# A group's trees, each a tmux session and the lemons in it. The first tree is the lead's.
# All invented: nothing here should resemble a real repo, person or branch.
_OPUS, _SONNET, _HAIKU, _FABLE, _SOL = (
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "claude-fable-5-1",
    "gpt-5.6-sol",
)
_GROUPS: dict[str, list[tuple[str, list[Lemon]]]] = {
    "storefront": [
        (
            "storefront-lead",
            [Lemon("AmberKit", "storefront-lead", "running", "hq", "claude", _SONNET)],
        ),
        (
            "web-signup",
            [
                Lemon("RoanFin", "signup-flow", "", "storefront-lead", "claude", _OPUS),
                Lemon("TealOwl", "review-signup", "review", "signup-flow", "codex", _SOL),
            ],
        ),
        (
            "search-facets",
            [Lemon("MossDew", "facet-counts", "merge", "storefront-lead", "claude", _OPUS)],
        ),
        (
            "checkout-flow",
            [Lemon("PlumBay", "checkout-retry", "blocked", "storefront-lead", "claude", _SONNET)],
        ),
        (
            "cart-totals",
            [Lemon("WrenFig", "cart-rounding", "done", "storefront-lead", "claude", _SONNET)],
        ),
        (
            "image-cdn",
            [Lemon("KelpAsh", "image-resize", "running", "storefront-lead", "claude", _OPUS)],
        ),
    ],
    "billing": [
        ("billing-lead", [Lemon("IvyLark", "billing-lead", "", "hq", "claude", _SONNET)]),
        (
            "billing-fix",
            [
                Lemon("CedarJay", "invoice-tz", "alert", "billing-lead", "claude", _OPUS),
                Lemon("FoxGlen", "review-invoice-tz", "review", "invoice-tz", "codex", _SOL),
            ],
        ),
        (
            "refund-api",
            [Lemon("QuillMoth", "refund-endpoint", "done", "billing-lead", "claude", _SONNET)],
        ),
        ("tax-rates", [Lemon("NettleRoe", "tax-table", "review", "billing-lead", "claude", _OPUS)]),
    ],
    "docs": [
        ("docs-lead", [Lemon("DuneWren", "docs-lead", "", "hq", "claude", _HAIKU)]),
        ("docs-site", [Lemon("OakPip", "docs-search", "running", "docs-lead", "claude", _SONNET)]),
        (
            "api-reference",
            [Lemon("BrineElk", "openapi-gen", "blocked", "docs-lead", "claude", _OPUS)],
        ),
        (
            "changelog-bot",
            [Lemon("TarnMink", "changelog-draft", "merge", "docs-lead", "claude", _HAIKU)],
        ),
        (
            "tutorials",
            [Lemon("SorrelVee", "quickstart-rewrite", "review", "docs-lead", "claude", _SONNET)],
        ),
    ],
    "infra": [
        ("infra-lead", [Lemon("SageToad", "infra-lead", "", "hq", "claude", _SONNET)]),
        (
            "ci-cache",
            [
                Lemon("LarkRye", "cache-keys", "merge", "infra-lead", "claude", _OPUS),
                Lemon("WispCod", "review-cache-keys", "", "cache-keys", "codex", _SOL),
            ],
        ),
        ("node-pools", [Lemon("HazelNew", "pool-sizing", "review", "infra-lead", "claude", _OPUS)]),
    ],
}
# Lemons in no group stand in the packhouse; HQ is the one the groups' leads descend from.
_LOOSE = [
    ("hq", [Lemon("PearLemon", "hq", "", "", "claude", _FABLE)]),
    ("scratch-notes", [Lemon("ClayVole", "scratch", "", "", "claude", _HAIKU)]),
]

# Each block's top-left corner and size, in grove units, as a 2x2 around the packhouse.
_PLOTS = {
    "storefront": (8, 3, 92, 24),
    "billing": (118, 4, 84, 22),
    "docs": (8, 34, 92, 24),
    "infra": (126, 37, 76, 20),
    "": (94, 27, 24, 7),
}
# Where each tree stands in its block (its crown's middle and the line its trunk starts on),
# staggered so no two trees line up, with each block's lead nearest the packhouse. ":lead" is
# the lead's spot, whichever tree leads.
_SPOTS = {
    "storefront": {
        ":lead": (78, 16),
        "web-signup": (60, 8),
        "image-cdn": (60, 19),
        "search-facets": (43, 14),
        "checkout-flow": (28, 7),
        "cart-totals": (14, 17),
    },
    "billing": {
        ":lead": (13, 14),
        "billing-fix": (31, 8),
        "refund-api": (46, 14),
        "tax-rates": (60, 8),
    },
    "docs": {
        ":lead": (78, 9),
        "docs-site": (62, 18),
        "api-reference": (46, 8),
        "changelog-bot": (30, 17),
        "tutorials": (13, 9),
    },
    "infra": {":lead": (12, 9), "ci-cache": (32, 13), "node-pools": (50, 8)},
}

_HOUR = 3600


def _seed() -> None:
    assert db.get_db_path() == demo.DB, db.get_db_path()
    demo.DB.parent.mkdir(parents=True, exist_ok=True)
    demo.DB.unlink(missing_ok=True)
    shutil.rmtree(demo.BRIEFS, ignore_errors=True)
    shutil.rmtree(Path(demo.ENVIRONMENT["LEMONAID_STATE_DIR"]), ignore_errors=True)
    demo.BRIEFS.mkdir(parents=True)
    Path(demo.ENVIRONMENT["LEMONAID_CONFIG"]).write_text(demo._config())

    trees = [
        (group, session, lemon)
        for group, sessions in [*_GROUPS.items(), ("", _LOOSE)]
        for session, lemons in sessions
        for lemon in lemons
    ]
    ids = {lemon.task: f"{lemon.name}.{lemon.task}" for _, _, lemon in trees}
    now = time.time()
    with db.connect() as conn:
        for i, (group, session, lemon) in enumerate(trees):
            channel = f"{lemon.backend}:grove-{i}"
            path = demo.BRIEFS / f"{lemon.task}.md"
            path.write_text(
                f"---\ntype: Brief\nbrief-id: {ids[lemon.task]}\n"
                + (f"status: {lemon.status}\n" if lemon.status else "")
                + f"---\n# {lemon.task}\n\n## Now\n\nWorking.\n"
            )
            db.add(
                conn,
                channel,
                "",
                session,
                {
                    "tty": f"/dev/ttys{900 + i}",
                    "cwd": str(Path.home() / "src" / session),
                    "tmux_session": session,
                    "tmux_window": "2" if lemon.task.startswith("review") else "1",
                    "model_provider": "openai" if lemon.backend == "codex" else "anthropic",
                    "model": lemon.model,
                },
                switch_source="tmux",
                created_at=now - (i * 7 + 3) * _HOUR / 5,
                # A lemon with no status and nothing unread is drawn dimmed; unread, plain grey.
                status="read" if lemon.status else "unread",
            )
            identity.ensure(conn, path)
            attached.attach(conn, channel, path.resolve())
            if group:
                groups.replace_memberships(conn, ids[lemon.task], [group])
        for _, _, lemon in trees:
            if lemon.parent:
                links.set_parent(conn, ids[lemon.task], ids[lemon.parent])


def _arrange() -> None:
    """Lay the grove out once, then write the blocks' plots and the trees' spots over it."""
    subprocess.run(
        [sys.executable, "-m", "lemonaid.cli", "grove", "show", "--plain"], capture_output=True
    )

    def place(before: dict[str, ty.Any]) -> dict[str, ty.Any]:
        saved = copy.deepcopy(before)  # `update` saves only a result that differs from what it read
        for name, (x, y, w, h) in _PLOTS.items():
            saved["plots"][name].update(x=x, y=y, w=w, h=h)
        for group, spots in _SPOTS.items():
            for key, (x, y) in spots.items():
                saved["trees"][group][key].update(x=x, y=y)
        return saved

    state.update(place)


def _stage(keys: list[str], columns: int, rows: int) -> None:
    demo._tmux("kill-server")
    _seed()
    _arrange()
    demo._tmux(
        "-f", "/dev/null", "new-session", "-d", "-s", "demo", "-n", "grove",
        "-x", str(columns), "-y", str(rows), "-c", str(Path.home()),
    )  # fmt: skip
    for name, value in demo.ENVIRONMENT.items():
        demo._tmux("set-environment", "-g", name, value)
    demo._tmux("set-option", "-g", "status", "off")
    demo._tmux(
        "respawn-pane", "-k", "-t", "demo:grove",
        sys.executable, "-m", "lemonaid.cli", "grove", "open",
    )  # fmt: skip
    time.sleep(4)
    for key in keys:
        demo._tmux("send-keys", "-t", "demo:grove", key)
        time.sleep(1)
    print(f"staged on tmux -L {demo.SERVER}; render it with scripts/demo-screenshot.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keys", nargs="*", default=[], help="keys to press once it is up")
    parser.add_argument("--columns", type=int, default=232)
    parser.add_argument("--rows", type=int, default=62)
    parser.add_argument("--kill", action="store_true", help="tear down the server and its state")
    args = parser.parse_args()

    if args.kill:
        demo._kill()
        return

    _stage(args.keys, args.columns, args.rows)


if __name__ == "__main__":
    main()
