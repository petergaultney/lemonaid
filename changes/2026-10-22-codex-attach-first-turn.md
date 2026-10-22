# Patch

- **`brief attach --self` and the other `--self` brief commands work for a Codex lemon that has not finished its first turn.** They used to fail with `No inbox session on channel`, because the inbox row is first written when a turn ends; a thread with a rollout and no parent now resolves from its thread ID. Threads with no rollout, and spawned ones, still get no brief.
