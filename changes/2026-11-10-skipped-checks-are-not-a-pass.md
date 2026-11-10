# Patch

#### Fixed

- **`watch pr` no longer reports "CI passed" for a head whose checks were all skipped or neutral.** CI counts as passed once at least one check succeeded and none is pending or failed; a head with only skipped checks keeps waiting. The merge-readiness test uses the same rule.
