# Minor

#### Added

- **Audit log of place opens and tosses.** `place open` and `place toss` (including dry runs, refusals and declined confirmations) append a JSON line to `logs/places.log` in the state directory, recording the place, session, flags, outcome and who ran it (the caller's Brief-ID, else its parent process).
- **`place log [<key>]`** prints the last events from that log, for answering who closed a place.
