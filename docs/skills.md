# Skills

Lemonaid ships skills that teach a lemon to use its commands: `watch-doc` (wait for Relay
Comments on a document, then reply in the thread) and `watch-pr` (wait for pushes, review
activity, conflicts and failed CI on a GitHub PR). `lemonaid skills install` puts them
where Claude Code and Codex look for skills.

```bash
lemonaid skills install                        # every packaged skill, for every harness found
lemonaid skills install watch-pr --harness codex
lemonaid skills install --json
lemonaid skills install --print watch-doc      # the text only, to install it yourself
```

## Adding your own conventions

The packaged text names no particular user, repo or folder. To add yours, write one file
per skill in `~/.lemons/skills/<name>/`:

- `overlay.md` is appended after the packaged text. Use it for your own procedures, paths
  and review policy. It may not start with frontmatter, so the packaged name and
  description always apply, and it keeps following packaged updates.
- `SKILL.md` replaces the packaged text entirely, frontmatter included. Use it only to
  change a packaged paragraph; it stops following packaged updates.

Having both is an error. Rerun `lemonaid skills install` after editing either, or after
upgrading lemonaid; install reports which source each skill came from.

## Where it writes

Each skill is rendered once, to `~/.local/state/lemonaid/skills/<name>/SKILL.md`
(`LEMONAID_STATE_DIR` moves it). Each harness's entry is a symlink to that directory:

- Claude: `~/.claude/skills/<name>` (`$CLAUDE_CONFIG_DIR/skills` when that is set).
- Codex: `~/.codex/skills/<name>` (`$CODEX_HOME/skills` when that is set).

By default install covers each harness whose home directory exists; `--harness` picks
harnesses and creates their skills directory. An entry counts as lemonaid's when it is a
symlink resolving to the rendered copy, directly or through another link, such as a Codex
entry that links to Claude's. Anything else already at an entry (a directory, a file, or a
link elsewhere) is left alone and reported as refused, and install exits 1. Move it aside
yourself if you want lemonaid's version. The same goes for the rendered directory: one
lemonaid didn't create (it has no `.lemonaid-skill` marker) is never written to. After linking, install reads each entry's
`SKILL.md` back and refuses it unless it matches.

`LEMONAID_CLAUDE_SKILLS_DIR` and `LEMONAID_CODEX_SKILLS_DIR` replace the two skills
directories outright, for tests and `scripts/sandbox`.
