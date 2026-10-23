# Patch

#### Fixed

- **A quiet `git push` that lemonaid rewrites no longer forces a permission prompt.** The hook now returns no permission decision, so the rewritten command follows the session's own permission mode, including auto mode.
