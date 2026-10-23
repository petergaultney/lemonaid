# The grove

> **Beta.** The grove is new and still changing. Its keys, its drawing, its commands and their JSON, and the layout files it keeps (`grove.json` and `grove-view.json` in lemonaid's state directory) may all change between releases without notice or migration. A release may lay out a grove afresh. Don't build on the formats yet.

The grove is a map of your lemons that keeps each one in the same place, so you can find a lemon by where it lives instead of scanning a list whose order changes with every status. Press `Space` in `lma` to open it, and `Space` again to close it. In tmux, from the sidebar or any pane too small for a map, it opens in a popup over the whole window instead, with a 3-cell margin (`popup_margin` in `[tmux-session]`). To open that popup from anywhere, bind a tmux key by adding what this prints to your tmux.conf:

```sh
lemonaid tmux popup grove --binding Space --title ' lemon grove '
```

This replaces tmux's default `prefix Space` (`next-layout`). Choosing a lemon in the popup switches the window you opened it over to that lemon and closes the popup.

The popup is lemonaid's fast tmux popup, which any app can use: the grove keeps running in a hidden tmux session named `_lma_grove`, as the scratch pane's inbox lives in `_lma_scratch`, and the popup shows that session, already drawn. `lma` starts it in the background when it opens inside tmux, and one from an older install is replaced. There is one grove, so opening it on one client closes it on any other, and a choice always switches the client it shows on. See [tmux.md](tmux.md#fast-popups).

- **A group is a block:** a patch of ground with its own color, outline, texture and signpost.
- **A tree is a terminal session** (a tmux session; for lemons outside one, their directory). An author and its reviewer share a tree. Its tag shows the name given to its main lemon, in the inbox or with `inbox rename`, and otherwise its session's name.
- **Lemons hang on their tree,** colored by brief status: the inbox's yellow for `blocked`, green for `merge`, brown for `review`, red for `alert`, teal for `running`, blue (hollow) for `done`, grey otherwise. A lemon mid-turn pulses slowly, and so does its tree's tag. Idle lemons are dimmed but never hidden: the grove shows hidden and folded lemons too, so nothing moves out of its spot.
- **The lead tree** (the group's lead, as the inbox works it out) stands nearest the packhouse, flies a pennant in its block's color, and has a star and the letter `l`, and its lead lemon comes first on it. HQ, the lead of the lemons in no group, gets `l` in the packhouse.
- **The packhouse** at the grove's middle holds the lemons in no group, HQ among them, each session as a bay. It's numbered `0`.
- **Roads and a stream** are landmarks: laid once, saved with the layout, and drawn under the blocks so they show in the gaps. A road crosses the stream on a bridge.

## Keys

| Keys | What they do |
|------|--------------|
| a digit | Zoom into that block. The inbox shows each lemon's key on its row, and typing one there jumps the same way. Blocks are numbered in the inbox's group order, so `2` is the second group in your list; lemons in no group are `0`. A second digit reaches block 10 and up (`1` `0`). |
| a letter | Jump to the first lemon on that tree. `l` is the lead tree. |
| a capital | Jump to the second lemon on that tree, such as its reviewer. A tree's main lemon is always first: a lemon whose brief is hidden (a reviewer's) comes after one whose brief isn't, then the lower window, then the older lemon. |
| a letter, then a number | On a tree with three or more lemons the letter opens it, and its lemons are numbered in the order they started. |
| `Alt`+`r` | Rename something, choosing it first: type a tree's letter (after its block's digit in the grove view), and the bottom line names its tmux session; the letter again, or an arrow, moves on to each of its lemons in turn. `enter` asks for the new name in a dialog, `esc` stops. A session keeps its tree's spot and letter; a lemon gets a new display name, as `r` gives one in the inbox, and an empty name clears it. |
| arrows | Pan the grove when it is too big for the screen, 2 columns or 1 row at a time (`grove_pan_columns` and `grove_pan_rows` in `[tui]`); it shrinks to fit only so far, so its trees stay readable. |
| `Shift` and an arrow | Move the view a whole screen that way. |
| `Shift` and a digit | Jump to a screen-sized part of the grove around the packhouse: `1` north, then clockwise to `8` north-west (`!@#$%^&*` on a US keyboard). `Shift`+`0` or `Home` centers the packhouse. `Alt` and a digit does the same on any keyboard. The grove opens where you left it. |
| `/` | Search Brief-IDs, then sessions and names. Blocks without a match fade; when every match is in one block, the grove zooms to it. `↑`/`↓` choose, `enter` jumps. |
| `esc` | Back out one step: out of a tree, out of a block, out of the grove. |
| `Space` | Close the grove from anywhere in it, except while typing a search. |

So `2c` always means the same tree, `2C` its second lemon, and `2c3` the third lemon on it. In the grove view each tag shows its tree's whole key, as `2c`; zoomed into a block, just the letter. A click on a block zooms into it, and a click on a tree acts like its letter.

Zoomed into a block, each tree lists its lemons with their Brief-ID, status, model and context use.

Change the key with `grove` in `[tui.keybindings]`.

## Places that stay put

The first time lemonaid sees a group it gives it a plot of ground near the middle of the grove, and the first time it sees a tree it gives the tree a spot in its block, as near the block's lead as it fits with room to spare (else near its first tree, and a block's first tree near the packhouse), and a letter, taken from the words that tell it apart. Neither moves after that. A tree with no room left in its block takes more ground for the block, on whichever side is free of other blocks; when none is, it stands just past the block's edge, where the block's view still shows it, and `lemonaid grove resize` or `move` makes room.

- **A group that ends leaves open ground.** The outline stays, unnamed, and the next new group takes the open ground nearest the middle, so the grove doesn't hollow out.
- **A tree that goes leaves a bare tree, with no leaves, in its spot.** The spot is kept for 30 days in case its session comes back; the next new tree in that block takes the oldest free spot.
- **New trees start small.** A tree whose oldest lemon is less than a day old is a sapling, and under three days a young tree. Every tree in a crowded block is drawn smaller, and grows again as the block empties.
- **Reordering groups renumbers blocks** but doesn't move them, so the digits always match the inbox.

The layout is saved in `grove.json` in lemonaid's state directory (`~/.local/state/lemonaid`, or `LEMONAID_STATE_DIR`), per machine.

## From the command line

```bash
lemonaid grove open              # the grove full-screen here; choosing a lemon switches to it
lemonaid tmux popup grove        # the same, in a tmux popup over this client
lemonaid grove show              # draw the grove in this terminal, once
lemonaid grove show 2            # draw block 2 zoomed in
lemonaid grove show --plain      # characters only
lemonaid grove show --json       # blocks, trees, spots, letters and lemons
lemonaid grove move 2 40 10      # put block 2's top-left corner at column 40, row 10
lemonaid grove resize oria 60 18 # by digit or by group name
lemonaid grove reshape 2 6       # 2 is an ellipse, 12 nearly a rectangle
lemonaid grove clear-open        # forget open ground left by groups that ended
```

The grove is 210 columns by 60 rows at full size. A larger grove is drawn smaller to fit the screen. `show --json` is meant for lemons: one can read the layout, propose a tidier one, and apply it with `move`, `resize` and `reshape` once you agree.
