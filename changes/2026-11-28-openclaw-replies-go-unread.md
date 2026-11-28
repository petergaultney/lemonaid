# Patch

#### Fixed

- **An OpenClaw lemon's row goes unread when its turn ends,** as a Claude lemon's does, so its replies notify. A final message matching `[inbox] auto_read` leaves it read. Needs `lemonaid openclaw observe`.
- **The grove counts an OpenClaw lemon's age from its last turn,** not from when its row was made.
