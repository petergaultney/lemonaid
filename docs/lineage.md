# Parent links

A lemon's parent is the lemon that handed it its work. Lemonaid records the link between the two Lemon-IDs, which live in the briefs, so it belongs to the work rather than to a harness session. Resuming, starting a new session on the same brief, or renaming the brief all keep it. Nothing about the link depends on tmux.

```bash
lemonaid lemon parent --self                        # my parent's Lemon-ID, or "none"
lemonaid lemon parent <lemon> --set self            # I am <lemon>'s parent
lemonaid lemon parent <lemon> --set <other>         # or name another parent
lemonaid lemon parent <lemon> --clear
lemonaid lemon children --self                      # Lemon-ID, Status:, channel, brief path
lemonaid place open feat/x --brief <file> --parent self
lemonaid lemon start work:4 --brief <file> --parent self
lemonaid tell --parent "PR is up"
lemonaid tell --child <lemon> "Rebase on main"
```

A `<lemon>` is a Lemon-ID, an attached lemon's channel, or a brief's name or path. The brief need not be attached yet, so a parent can name a child whose lemon hasn't started. Every command takes `--json`.

- **One parent per lemon.** `--set` replaces the parent. A lemon can't be its own parent, and a link that would make it its own ancestor is refused.
- **`--parent` on `place open` and `lemon start` requires `--brief`.** The link is between two Lemon-IDs, and the child's comes from its brief. Without `--brief`, `place open` records nothing about lemons.
- **Checked before anything opens.** `place open` resolves the parent and checks the link first, and records it only once the place is open.
- **No parent means the default owner.** A lemon with no parent belongs to whoever you treat as the default, for many a control center; lemonaid doesn't record who that is.
- **In the brief view.** The sidebar, popup and `brief show` show the brief's title, its `Brief-ID:` and `Parent:` before its status, the parent named by its session when lemonaid knows it (``Parent: lemonaid HQ (`hq`.**BlessBar**)``). They list its `Children:` one per line, each child's `Status:`, its session's name and its brief name, just before `Done`.
- **Children for cleanup.** `brief children --self` gives each child's place, session, PRs and reviewers, and whether its place is ready to tear down (see `docs/for-lemons.md`). `lemon children --json` is the bare list: each child's brief `Status:` and whether a lemon is attached.
