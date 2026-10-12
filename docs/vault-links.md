# Vault paths that open in Obsidian

Lemons print paths to notes, such as `~/notes/Project Plans/launch.md`.
`lemonaid terminal vault-links` installs a terminal rule that makes such a path
open in Obsidian when you click it. It matches a `.md` path under a root in
[`[brief] vaults`](config.md#brief), written from `~` or in full, including
folder names with spaces.

```sh
lemonaid terminal vault-links iterm2
lemonaid terminal vault-links wezterm
```

Each run replaces lemonaid's own rule and leaves your other rules alone, so run it
again after changing `vaults`. `--dry-run` shows what would change, `--print`
prints the rule without changing anything, and `--remove` takes lemonaid's rule out.

A click runs `lemonaid terminal open-vault <path>`, which builds the
`obsidian://open` URL the same way briefs do (the vault is named after its
folder) and opens it. The rule records the full path of the `lemonaid` it was
installed by, so reinstall if that moves.

Because a match may contain spaces, a directory mentioned before a later `.md`
name on the same line, as in `~/notes/drafts/ and then read plan.md`, matches as
one path. Clicking it reports that the file does not exist instead of opening it.

## iTerm2

The rule is a Smart Selection rule, added to every profile (Settings > Profiles >
Advanced > Smart Selection). Cmd-click on a path runs it, and a double-click
selects the whole path, spaces included, so right-click then offers "Open in
Obsidian". A profile still on iTerm2's built-in rules gets those copied in
first, so they keep working.

For a file that exists, Cmd-click normally goes to the profile's Semantic
History setting (open in an editor, say) before any Smart Selection action. The
install therefore turns on the advanced setting "Check smart selection actions
before existing files on cmd-click?" (`PrioritizeSmartSelectionActions`). It
applies to every Smart Selection rule with an action, not only this one.
`--remove` leaves it on; turn it off in Settings > Advanced if you no longer
want it.

The rule's action runs a shell command with the matched path in it, so in iTerm2
a path containing any of ``;&|$`\"'()`` does not match. Such text can't start
a second command when clicked, even if printed by something you don't trust.

iTerm2 reads its profiles when it starts, so restart it after installing. If it
saves its profiles before then, for example after you edit one in Settings, it
writes the old rules back; `--dry-run` after the restart shows whether the rule
is still there. If iTerm2 loads its settings from a custom folder, pass that
plist with `--iterm2-plist`.

## WezTerm

Lemonaid writes `lemonaid_vault_links.lua` beside your `wezterm.lua` (change the
directory with `--wezterm-dir`), and rewrites it on every install. Add these lines
to `wezterm.lua` once, after `config` is built and after any `hyperlink_rules` you
set, so the rule is appended to them:

```lua
local ok, vault_links = pcall(require, 'lemonaid_vault_links')
if ok then
  vault_links.apply(config)
elseif not vault_links:find("module 'lemonaid_vault_links' not found", 1, true) then
  wezterm.log_error(vault_links)
end
```

The install prints them until `wezterm.lua` mentions the module. WezTerm keeps
starting after `--remove` deletes the module, and logs an error if the module
fails to load for any other reason. WezTerm runs the click without a shell, so
its rule matches any characters except a newline, backtick, `<`, `>`, `[` and `]`.

## Under tmux

Both terminals match the text tmux draws on screen. A path tmux wrapped onto a
second line, or one cut off at a pane's edge, matches only up to the break.
