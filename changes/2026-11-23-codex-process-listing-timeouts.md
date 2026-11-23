# Patch

#### Fixed

- **lemonaid can tell which Codex lemons run on a busy Mac again.** Its process listing timed out about once a second; it now asks `ps` for terminal device numbers instead of names, which cost most of a second, and the scout host's Codex scouts share one listing.
- **`lemon restart` no longer fails when the lemon's terminal closes and a new one takes its name.**
