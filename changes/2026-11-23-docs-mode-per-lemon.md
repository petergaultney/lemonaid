# Minor

#### Added

- **`[docs]` names the always-loaded docs, and `--docs` sets a lemon's docs mode.** `[docs] classic` takes the place of `[codex] context_doc`, which is still read when it is unset. `lemon start --docs` and `place open --docs` override `[docs] mode` for one lemon, and its sessions keep the mode through resumes; `packages` isn't built yet and starts the lemon in `classic`.
