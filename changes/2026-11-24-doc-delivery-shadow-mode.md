# Minor

#### Added

- **Docs can say which lemons get them and which actions bring them back, and lemonaid logs what each lemon would be given.** A doc under `[docs] roots` names its package, or the lemons a package is for, and its triggers on commands, edits, new files and prompts, in its frontmatter. `lemonaid hooks docs` logs each would-be delivery to `doc-deliveries.jsonl`, once per context window, and delivers nothing yet; `lemonaid docs` shows a session's deliveries, the lemons holding a doc, and every doc's package and triggers. Run `lemonaid hooks install` to add the hook, and trust it in Codex's `/hooks`.
