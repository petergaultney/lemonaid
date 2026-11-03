# Patch
`lemonaid brief section rm` now exits nonzero with `No heading 'X'` when the brief has no such heading, instead of printing the path and leaving the brief unchanged. Heading arguments with leading `#`s, such as `'## Waiters'`, now match the same heading as the bare name across `section` and the bullet verbs.
