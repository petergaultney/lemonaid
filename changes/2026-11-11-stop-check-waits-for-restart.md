# Patch

#### Fixed

- **The Stop check waits for a restarting scout host instead of saying the push scout did not start.** A turn that ended while `lemonaid watch restart` was restarting the host got a false "NOT pushing" block; the check now waits up to a minute for the new host.
