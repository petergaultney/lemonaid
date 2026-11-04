# Patch

`lemon restart` now waits up to 10 seconds, not 3, for the old harness to finish exiting before it respawns the pane, so a loaded machine no longer leaves a restart half done; the "unmanaged jobs" error also names the processes still on the terminal.
