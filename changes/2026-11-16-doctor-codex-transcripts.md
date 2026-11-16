# Patch

#### Fixed

- **`lemonaid tmux doctor` counts a Codex lemon as restorable when its rollout is on disk.** It looked for every transcript under Claude's projects, so it reported each Codex lemon as `transcript not on disk`, and it now asks the same question restore does. It also no longer counts a row restore has no resume command for, such as an OpenClaw row without a `session_key`.
