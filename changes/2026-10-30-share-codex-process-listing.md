# Patch

- Codex scouts share one `lsof` listing of Codex's open rollouts, instead of each running its own every 30 s to check its thread is still open. With 35 Codex scouts that was about 13% of a core.
