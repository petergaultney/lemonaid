# Minor

#### Changed

- **Every default inbox key that changes something immediately is now a capital letter.** Typing lowercase into the inbox by mistake no longer archives, marks read, pins, undoes, or flips the pane; `Escape` still backs out of anything, and now also returns from history to the inbox. The new defaults are `M` mark read, `Alt`+`m` mark unread, `A` archive, `Z` undo, `P` pin, `F` flip the pane, and in a brief view `D` more detail. Keys that only open a dialog or a view are unchanged. The Claude patch key moves from `P` to `Ctrl`+`t`.
- **New `dialog_accept` setting** names the key that accepts an error dialog's offer (archive, copy the resume command); it defaults to `A`.
- **Your `[tui.keybindings]` overrides are untouched.** Only the defaults moved; see [keybindings.md](../docs/keybindings.md) to keep an old key.
