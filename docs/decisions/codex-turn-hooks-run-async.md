---
type: Design
created: { at: 2026-11-20T07:21:40-05:00, by: FluidSip }
responsible-parties:
  - Peter Gaultney
contributors:
  - FluidSip
status: stable
---

# Codex turn hooks run asynchronously

Decided 2026-11-20, in [lemonaid#566](https://github.com/petergaultney/lemonaid/pull/566).

## Decision

`lemonaid codex turn` is installed with `"async": true` on UserPromptSubmit, PreToolUse, PostToolUse, Interrupt and PostModelRequest. Codex doesn't wait for it, and runs up to 8 async hooks at once, so its reports can reach the inbox in any order.

The recorded state tolerates any order instead (`codex/turns.py`, `inbox/db.py`):

- A row keeps the latest started turn ID and the latest ended turn ID. Codex's turn IDs are UUIDv7, so they sort by start time.
- Each ID only moves forward, in a single SQL `UPDATE`.
- A lemon is mid-turn exactly when its latest start is newer than its latest end.
- `tests/test_codex_turns.py` checks every order of two turns' starts and ends.

## Alternative: synchronous hooks

Install the state-changing hooks (UserPromptSubmit, Interrupt) without `async`, so Codex finishes each one before the next and they arrive in order.

Not chosen because Codex would wait for a lemonaid process to start and finish before every prompt, and before every tool call if PreToolUse stayed synchronous too. The turn end also comes from the notify program, not these hooks, so the stored state would need to tolerate a late report anyway.

Revisit if a hook has to record something that can't be made monotonic like this, or if Codex starts running a thread's hooks in order.
