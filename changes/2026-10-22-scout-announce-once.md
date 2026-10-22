# Patch

#### Fixed

- **A lemon is told about its push scout once per session, not on every restart.** Restarts after an upgrade or `lemonaid watch restart` no longer send the "push scout started" message.
