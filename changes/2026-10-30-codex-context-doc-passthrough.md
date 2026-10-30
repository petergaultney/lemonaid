# Minor

#### Added

- **Codex sessions can start with your always-loaded docs.** Set `[codex] context_doc` to a Markdown file and lemonaid's Codex SessionStart hook passes it, with the files its `@` imports name, to each new thread and again after `/clear` and compaction, but not on resume or fork. `lemonaid hooks install --harness codex` now sets `"additionalContextLimit": 0` on that hook so Codex keeps the whole text; approve the changed hook in Codex's `/hooks` once after upgrading.
- **Codex's `/hooks` names lemonaid's hooks.** `lemonaid hooks install --harness codex` gives each one a `statusMessage` such as `lemonaid: session-start` instead of leaving it as "Unnamed hook", and updates installed ones in place; approve them again in `/hooks`.
