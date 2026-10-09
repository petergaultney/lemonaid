# Subscription usage

`lemonaid usage` shows how much of each Claude and Codex subscription limit window is used, and how that compares with the straight line to the window's reset.

```bash
lemonaid usage          # one line per limit window, then exit
lemonaid usage --watch  # block until an alert, print it, and exit
```

On a terminal, two parts of each line are colored, on separate scales.

- **Used, with its pace.** Pace is usage so far divided by the share of the window elapsed, where 1.0 is exactly on pace. The colors are green at 0.8, yellow at 1.15, orange at 1.4 and red at 1.8 by default (set with `pace_color_ratios`), so being exactly on pace is a yellow-green. Cyan and blue are further below green than orange and red are above it. The scale is logarithmic, so running at twice the pace and at half the pace are equally far apart. With too little of the window elapsed to judge, it is dim.
- **Projected at reset.** The usage expected at reset if the pace so far continues, on a linear scale from 0 to 100% of the cap: blue at 0, green at 55%, yellow at 75%, orange at 90%. Red means reaching or passing the cap, so anything less says how close the window is expected to come.

`--no-color` or `NO_COLOR` turns color off, and output that isn't a terminal is never colored.

Example line: `codex primary (10080min): 77% used (pace 2.85x), elapsed 27%, projected 285% at reset, runs out Fri 10:04 EDT, resets in 4d 2h (Tue 23:30 EDT)`.

## Alerts

`--watch` prints one line per alert and exits, so a Claude background Bash task wakes its session once. Rearm it after each wake.

- **A step crossing.** Usage crosses a multiple of `step_percent` (20 by default) in any window. The line also gives the elapsed share of the window and either the projected percentage at reset or the projected run-out time. A window seen for the first time, or after it resets, is baselined silently at its current step.
- **Over pace.** Usage divided by the elapsed share of the window projects past `pace_over_percent` (100 by default) at reset. The line says when it would run out and how long before the reset that is. It fires once per window.
- **Back on pace.** After an over-pace alert, the projection falls under `pace_recovered_percent` (90% of `pace_over_percent` by default). It fires once, then over-pace can fire again.

Pace alerts are skipped until `pace_min_elapsed_percent` (5 by default) of the window has passed. A window already over pace when first seen alerts at once.

Which alerts have fired is kept in `usage/alerted.json` under the state directory, so restarts don't repeat them. Delete it to start over.

Thresholds are set in [`[usage]`](config.md#usage).

## Where the data comes from

- **Codex:** the `rate_limits` in `token_count` events of the newest rollouts under `~/.codex/sessions`.
- **Claude:** Claude Code passes `rate_limits` (`five_hour` and `seven_day`) to its statusLine command. `lemonaid-claude-statusline` saves them to `usage/claude-rate-limits.json` under the state directory on every render. This is undocumented Claude Code behavior, seen in 2.1.294. Use `lemonaid-claude-statusline` as the statusLine command, as described in [claude.md](claude.md). A statusLine command that wraps it must pass stdin through unchanged.

Data updates only while a session of that harness is active.
