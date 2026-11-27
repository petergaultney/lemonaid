# Patch

#### Changed

- **An OpenClaw lemon's scout and doc waiter read its turns from `lemonaid openclaw observe`.** They learn whether the session is mid-turn, and when its turn started and ended, from what the observer records in the inbox, instead of each asking the gateway every 5 seconds. Without the observer running, they no longer hold batches for a running turn.
