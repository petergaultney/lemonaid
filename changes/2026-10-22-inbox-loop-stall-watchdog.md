# Minor

#### Added

- **The inbox logs each moment its event loop is blocked for over 100 ms, and where.** A log line reads `loop blocked 920 ms in inbox.presence._harness_ttys -> subprocess.run`; `[tui] show_loop_stalls = true` also shows the longest stall of the last minute in the status line.
