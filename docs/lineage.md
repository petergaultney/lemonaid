# Parent links

A lemon's parent is the lemon that handed it its work. Lemonaid records the link between the two Lemon-IDs, which live in the briefs, so it belongs to the work rather than to a harness session. Resuming, starting a new session on the same brief, or renaming the brief all keep it. Nothing about the link depends on tmux.

```bash
lemonaid lemon parent --self                        # my parent's Lemon-ID, or "none"
lemonaid lemon parent <lemon> --set self            # I am <lemon>'s parent
lemonaid lemon parent <lemon> --set <other>         # or name another parent
lemonaid lemon parent <lemon> --clear
lemonaid lemon children --self                      # Lemon-ID, Status:, channel, brief path
lemonaid place open feat/x --brief <file> --parent self
lemonaid tell --parent "PR is up"
lemonaid tell --child <lemon> "Rebase on main"
```

A `<lemon>` is a Lemon-ID, an attached lemon's channel, or a brief's name or path. The brief need not be attached yet, so a parent can name a child whose lemon hasn't started. Every command takes `--json`.

- **One parent per lemon.** `--set` replaces the parent. A lemon can't be its own parent, and a link that would make it its own ancestor is refused.
- **`--parent` on `place open` requires `--brief`.** The link is between two Lemon-IDs, and the child's comes from its brief. Without `--brief`, `place open` records nothing about lemons.
- **Checked before anything opens.** `place open` resolves the parent and checks the link first, and records it only once the place is open.
- **No parent means the default owner.** A lemon with no parent belongs to whoever you treat as the default, for many a control center; lemonaid doesn't record who that is.
- **In the brief view.** The sidebar, popup and `brief show` put `Parent:` and `Children:` (with each child's `Status:`) under a brief's card.
- **Children for cleanup.** `lemon children --json` gives each child's brief `Status:` and whether a lemon is attached, which is what a parent checks before tearing down a finished child's place. Links say which lemons to check, not which windows or directories are theirs.
