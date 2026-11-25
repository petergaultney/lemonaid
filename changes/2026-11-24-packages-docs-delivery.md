# Minor

#### Added

- **`--docs packages` starts a lemon with the packages that are for it, and the docs hook delivers.** A Claude lemon gets its packages in its system prompt, with the always-loaded docs turned off, and `lemonaid claude resume` passes the same flags again; a Codex lemon gets them from the SessionStart hook. Triggers now give their section, refuse a call once for a `before` rule, and keep each delivery to Claude under 10,000 characters. A lemon whose packages can't be built starts in `classic`, with a warning.
- **A package or trigger can name a group or a lead's lemons, with `group:` and `under:`.** Classic lemons get these too, and a doc new to a lemon's package, or a package it newly joined, reaches it at its next tool call. Everything else a classic lemon would be given is still only logged, as `shadow`. Run `lemonaid hooks install` again, since the docs hooks now run synchronously, and trust them in Codex's `/hooks`.
- **A skill overlay may carry frontmatter that isn't the skill's own,** such as a doc's packages and triggers; `lemonaid skills install` drops it. An overlay that sets `name` or `description` is still refused.
