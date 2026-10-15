# Restart preflight

Inspect whether one live Claude or dedicated Codex lemon can be restarted in its
own tmux pane:

```sh
lemonaid lemon restart <lemon> --dry-run --json
```

The target can be a Lemon-ID, channel, or attached brief name. Preflight checks
the native session and process generation, recorded tmux socket, transcript,
working directory, effective model and operating settings. It changes neither
the harness nor its watchers. Install Lemonaid's session hooks first; a native
hook observation must bind the session to its process.

Busy turns and transient input are refused unless `--force` is given. Force
never overrides uncertain process ownership or launch settings. A dead session
uses `lemonaid lemon resume`. Execution support builds on this preflight.
