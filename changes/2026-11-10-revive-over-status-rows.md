# Patch

#### Fixed

- **`lemonaid lemon resume --recreate` no longer crashes with a UNIQUE constraint error when the brief's live path already has Status or Needs timing rows.** The archived brief's timing rows replace them, and archiving over stale rows works the same way. A Lemon-ID already registered at the live path still refuses the revive.
