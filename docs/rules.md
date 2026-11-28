# Rule checks at the end of a turn

Lemonaid can check the message each lemon ends its turn with against a file of regexes, each naming a rule a match suggests the lemon broke. Every match is logged. A match can be reported to a lemon you name, which judges it, and a pattern that has proved itself can also tell the lemon the rule before its turn ends.

It reads only that final message, never tool calls. It names no rule itself: the patterns and the rules they cite are yours.

## Turning it on

1. Install lemonaid's hooks, if you haven't: `lemonaid hooks install`. The check runs in the `Stop` hook they install for Claude Code (`lemonaid claude waiter-check`) and Codex (`lemonaid hooks stop --harness codex`). Nothing new is installed for it, so Codex needs no new trust.
2. Write a pattern file (below) and name it in your config, with the lemon that hears of matches:

   ```toml
   [rules]
   patterns = "~/notes/rule-patterns.toml"
   report_to = "rules-desk"  # a Lemon-ID, channel or brief name `lemonaid tell` reaches
   ```

   Without `report_to`, matches are only logged.
3. Promote the file: `lemonaid rules check --promote`.

The hook never reads the pattern file itself. It reads the copy that `rules check --promote` writes after every check passes, so a half-saved edit or a sync conflict in the file changes nothing that runs. Edit the file, then promote again. Until the config names a file and that file has been promoted, the check does nothing.

## The pattern file

```toml
[[pattern]]
id = "merge-ask"
regex = '''(?i)\b(?:want me to|should i) merge\b|\bready to merge\?'''
rule_file = "rules.md"                    # relative to this file, absolute, or ~/...
rule_starts = "- **A PR ready to merge"   # the rule's paragraph or list item starts with this
mode = "report"                           # or "tell"; "report" when left out
say = "Set the Status to merge and don't ask."  # what a told lemon does now; tell mode needs it
cwd = "~/work/repo/*"                     # optional: only sessions whose working directory matches
match = ["Want me to merge it?", "CI is green. Ready to merge?"]
no_match = ["The user merged it.", "I resolved the merge conflict."]
```

`rule_file` and `rule_starts` point at the rule instead of copying it. When a `tell` pattern matches, the hook reads the rule from the file then, so the lemon gets its current wording. The rule is the line starting with `rule_starts` and what continues it: wrapped lines and nested list items, up to a blank line, a heading or the next item at its level.

`cwd` is a glob in `fnmatch`'s sense, so `*` crosses directories.

### What `rules check` checks

`lemonaid rules check` reads the configured file, or `--file`, and exits 1 listing every problem. `--promote` writes the copy only when there are none.

- Each regex compiles.
- No regex nests one quantifier inside another, such as `(\w+\s?)+`, the commonest way a regex backtracks for hours on a long message. Such a regex's examples aren't run.
- Every `match` example matches, every `no_match` example doesn't, each within half a second, and each pattern has at least one of each.
- Exactly one paragraph or list item in `rule_file` starts with `rule_starts`.
- Ids are unique, keys are known, and a `tell` pattern has `say`.

## Modes

- **`report`**: the match is logged and reported. The lemon hears nothing.
- **`tell`**: as `report`, and the lemon is also told the rule and `say`. The `Stop` hook holds its stop once with them as the reason, in both harnesses, so it can correct itself before you act on its message. A second stop goes through, as lemonaid's waiter check does.

### OpenClaw lemons

OpenClaw has no stop to hold, so `lemonaid openclaw observe` runs the check when a turn ends, on the turn's final message. A match is logged and reported as above, with the session key in place of a transcript. A `tell` pattern sends the rule and `say` to the lemon with `lemonaid tell` once its turn is over, and its scout delivers them as its next turn. A failed turn isn't checked.

Lemonaid reads only `mode`. Who moves a pattern from `report` to `tell`, and on what evidence, is up to whoever keeps the file.

## What a report says

The report is a `lemonaid tell` to `report_to`, sent from the lemon's channel so the message's sender is its return address. It names the pattern and the rule it cites, the mode, the working directory and transcript path, and about 300 characters around the match. The `tell` runs detached from the hook, so a slow delivery never holds a turn; its output goes to `rules/tell.log` in lemonaid's state directory.

Limits:

- One report per lemon and pattern a day. Later matches are only logged.
- At most 20 reports an hour across all lemons. Past that, matches are only logged, and the next report says how many were held.
- The session `report_to` names is never checked, since it writes about rules all day.

Every match goes to `rules/hits.jsonl` in lemonaid's state directory (`~/.local/state/lemonaid` unless `LEMONAID_STATE_DIR` moves it), with what happened to it: `reported`, `repeat`, `held`, or `logged` when there is no `report_to`.

The hook reads at most the last 20 KB of a message. Python's `re` has no timeout of its own, so the hook gives each search half a second and all of them two seconds; a pattern that runs out of time is skipped for that message and logged. `claude -p` sessions, subagents and spawned Codex threads aren't checked. Any error in the check is logged in one line to lemonaid's log and lets the turn end.

## Trying a pattern on past turns

```bash
lemonaid rules replay merge-ask --since 14d
```

`replay` runs patterns from the pattern file, promoted or not, over the final messages of every Claude and Codex turn since then, and lists each hit with its time, harness, working directory, excerpt and transcript, then a count per pattern. Name no ids to run every pattern. Run it before promoting a new pattern to count its false positives. A pattern that runs out of time on a message, as the hook would, is named with that message and not run on the rest. It reads Claude's transcripts under `~/.claude/projects` (`CLAUDE_CONFIG_DIR` moves it) and Codex's under `~/.codex/sessions` and `archived_sessions` (`CODEX_HOME` moves it), and leaves out subagents and spawned threads.
