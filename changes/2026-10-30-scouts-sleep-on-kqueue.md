# Minor

#### Changed

- **Idle push scouts sleep until something they watch changes.** On macOS the scout host wakes a lemon's scout on kqueue events for its brief, inbox, watched docs and files, children's briefs and session process, with a full check every 45 seconds, instead of polling every half second. A one-shot `watch --self` and the scouts on other platforms keep their timers.
