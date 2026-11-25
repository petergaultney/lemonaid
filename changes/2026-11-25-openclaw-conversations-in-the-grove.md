# Minor

#### Added

- **`lemonaid openclaw sync` makes every recent OpenClaw conversation a lemon.** Each Matrix room, Signal, WhatsApp or Telegram chat and agent main session active in the last 90 days gets a row in its agent's workspace, named for its agent and chat, and is archived when it goes quiet unless it has a brief. A lemon you archive stays archived. `lemonaid openclaw observe` runs it every minute until stopped, for a service beside the gateway. See [openclaw.md](docs/openclaw.md#every-conversation-in-the-grove).
- **Each OpenClaw conversation is its own tree in the grove,** rather than sharing one with every conversation in its agent's workspace.
- **Archiving an OpenClaw session archives its lemon,** and restoring the session brings the lemon back, as closing and resuming a Claude or Codex session does.
