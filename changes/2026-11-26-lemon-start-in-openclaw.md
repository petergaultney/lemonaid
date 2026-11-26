# Minor

#### Added

- **`lemon start` from an OpenClaw session opens a new, ordinary session of the same agent.** It is a root session, not a subagent, so OpenClaw sends the caller no run announcements or message notices; `--brief`, `--parent`, `--group`, `--name` and `--prompt` work as they do in a terminal. See [openclaw.md](docs/openclaw.md#starting-a-lemon-from-a-session).

#### Changed

- **Registering an OpenClaw session again keeps its lemon's name.** It used to rename it to its agent's id.
