# Minor

#### Added

- **OpenClaw gateway sessions can be lemons.** Inside a session, `lemonaid openclaw register --session-key <key>` gives it an inbox row (`openclaw:<key>`) that `--self` commands find again, so it can hold a brief, get mail and run `lemonaid watch --self --push`, whose scout delivers each batch as a gateway turn. See [openclaw.md](docs/openclaw.md#gateway-sessions-as-lemons).

#### Changed

- **`--self` inside an OpenClaw session never resolves to a Codex lemon.** It used to take the Codex thread OpenClaw runs the session on for a Codex lemon of its own.
- **Inside a systemd service, the scout host starts in a transient user unit of its own,** so restarting that service doesn't stop it.
