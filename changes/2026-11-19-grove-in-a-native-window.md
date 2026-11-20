# Minor

#### Added

- **The grove can open in a native window over your terminal (beta, macOS).** A tmux key summons it over the terminal's window, starting it the first time (`lemonaid grove window binding` prints the key's lines, which open the terminal grove on other systems), where it draws the grove in pixels and zooms smoothly. It does what the terminal grove does: jumps to a lemon on a click or its key, searches with `/`, edits lemons and blocks from a right-click or `Tab`'s select mode, and moves a tree, or moves or resizes a block or open ground, when you drag it. It needs the `web` extra: `uv tool install 'lemonaid-inbox[web]'`.
- **The tmux docs list the keys that work from any pane,** and `lemonaid for-lemons` tells a lemon how to set them up with you.
- **`grove show --json` gives each block's color, each tree's lead flag, size and packhouse bay, and the roads and stream.**

#### Changed

- **A block's lead tree can be moved farther from the packhouse.** Dragging, `grove plant` and `grove apply` no longer refuse it; `grove show --json` still warns (`lead-far`) when another tree stands nearer the packhouse.
