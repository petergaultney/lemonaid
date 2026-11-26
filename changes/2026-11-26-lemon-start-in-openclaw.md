# Minor

#### Added

- **`lemon start` from an OpenClaw session opens a new, ordinary session of the same agent.** It is a root session, not a subagent, so OpenClaw sends the caller no run announcements or message notices; `--brief`, `--parent`, `--group`, `--name` and `--prompt` work as they do in a terminal. See [openclaw.md](docs/openclaw.md#starting-a-lemon-from-a-session).

- **`brief handoff --to openclaw`** moves a brief into a new OpenClaw session, started the same way, once the outgoing lemon is ready. Use it to replace a subagent session with an ordinary one.

#### Changed

- **Registering an OpenClaw session again keeps its lemon's name.** It used to rename it to its agent's id.
