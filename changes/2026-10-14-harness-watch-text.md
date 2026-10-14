# Minor

#### Changed

- **Skills and hook text give each harness its own watch guidance.** Claude lemons are told what the push scout does for them and Codex lemons how to arm `--codex-thread`, and neither text mentions the other's mechanism. Each harness now has its own rendered copy of every skill (`<state>/skills/<harness>/<name>`), so `lemonaid skills install` repoints existing entries; `--print` takes `--harness` (default `claude`), and a skill, overlay or replacement can mark a harness-only section with `<!-- harness: claude -->` ... `<!-- /harness -->`.
- **Pushed batches, the session-start text and the child-brief reminder no longer say what not to do.** They state that lemonaid is watching for the lemon.
