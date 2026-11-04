# Patch

#### Fixed

- **lemonaid no longer reports a good delivery to a parked Claude session.** A Left Arrow on an empty Claude Code prompt moves the conversation to a background job, and the pane's process still takes a pushed message without running a turn, so events were lost. The push scout now sends nothing to a session whose listing has a `parkedJobId`, and its batches stay pending.
- **`tell` says that a parked Claude lemon will not read the message.** It names the background job, exits 1, and does not type into the pane. `lma` and `lemon doctor` show the lemon as not listening, and its parent wakes once, as for a deaf lemon.
