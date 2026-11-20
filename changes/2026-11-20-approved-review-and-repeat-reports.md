# Patch

#### Fixed

- **The task inspector lets a reviewer wait for the merge of a teammate's PR the user approved.** The task waits on the PR, so the reviewer needs neither a Status nor to close it.
- **A gone or exited lemon is no longer reported again after a brief blip.** A reported problem now ends only once the lemon stays healthy for the settle time, so a failed probe during `lemonaid watch restart` does not make the same report new.
