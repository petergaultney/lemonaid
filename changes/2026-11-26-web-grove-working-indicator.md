# Minor

#### Added

- **The web grove shows which lemons are mid-turn.** A lemon's page pulses a dot by its name and ends its conversation with a "working..." row where the next reply will appear, and the phone's bar pulses a dot on each working lemon, as its group list already did.
- **OpenClaw lemons show as working while their turn runs.** `lemonaid openclaw observe` records an OpenClaw session's turn from the gateway's events, so every grove pulses it from the turn's first event until it ends or fails.

#### Changed

- **Sending a lemon a message from its page marks it read.** An unread lemon never shows as mid-turn, so the turn your message started would otherwise not show.
