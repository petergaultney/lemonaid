# Minor

#### Added

- **The Stop hook can check each lemon's final message against your rule patterns.** Name the pattern file and who hears of a match in `[rules]`, then run `lemonaid rules check --promote`; see `docs/rules.md`. `lemonaid rules replay` tries patterns on past Claude and Codex turns before they go live.
