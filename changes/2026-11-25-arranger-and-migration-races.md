# Patch

- **`lma` draws an `[inbox] arrange` answer as soon as it arrives.** It used to wait for the next refresh that found something changed, up to five seconds after the inbox opened or the arranger restarted.
- **Processes opening a new inbox database at the same moment no longer fail midway through its migrations.** Three migrations released the migration lock early, so two processes could run the same migrations at once and one failed with an error such as `no such table: pending_briefs`.
