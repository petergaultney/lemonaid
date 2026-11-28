# Patch

#### Added

- **OpenClaw lemons get the end-of-turn rule check.** `lemonaid openclaw observe` checks a finished turn's final message against the promoted patterns. A `tell` pattern's rule reaches the lemon as its next turn, since there is no stop to hold.
