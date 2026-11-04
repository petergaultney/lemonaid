# Minor

#### Added

- **A contested Status is marked in the inbox and grove.** While a `status-claim` challenge is open, the card strikes through the status word and says why, the brief popup says **Status contested**, and the grove tags it `merge?`; the brief's Status itself is never changed.
- **`lemonaid task recheck --all | BRIEF...`** records a re-check request that the checker turns into a message. The default checker also asks a lemon to re-check when a file its Needs links to changed and its next turn left its Status and Needs alone, ending with your `[tasks.policy] recheck_text`.
- **`tell` prints the message's ID, and `lemonaid mailbox receipt ID` says `pending` or `delivered <time>`.** `tell` printed the message's path before.

#### Changed

- **The inspector sends each challenge once per set of facts.** A copy its lemon never received is replaced every `challenge_interval`; the doubling backoff and `max_challenge_interval` are gone.
