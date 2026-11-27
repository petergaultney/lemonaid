# Minor

#### Added

- **Watch sources: `lemonaid watch <name>` follows anything a plugin can read.** A source is a long-running command configured under `[[watch.sources]]`; lemonaid keeps the scheduling, cursors, delivery and ending of each subscription, and `lemonaid <name> ...` runs the plugin's own commands. The protocol is in `docs/source-plugins.md`.

#### Changed

- **Slack is now a watch source, `lemonaid-slack`, configured by default.** `lemonaid watch slack`, `lemonaid slack signin|status|signout` and the `[slack]` table work as before, and existing cursors carry over. A lemon that is told Slack needs a sign-in when you upgrade may hear it once more.
