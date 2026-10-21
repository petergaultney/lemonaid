# Minor

#### Changed

- **Briefs keep their metadata in YAML frontmatter.** New briefs start with a block holding `type: Brief`, `created: { at, by }`, `responsible-parties`, `contributors`, and the fields the `Brief-ID:`, `Status:`, `Parent:`, `Area:`, `Output-Doc:`, `Groups:`, `Hidden:` and `Name words:` header lines used to carry. The `# Title` follows the block.
- **Older briefs keep working and convert on their first edit.** Lemonaid still reads header lines, and moves them into a block the first time a verb changes the brief; `lemonaid brief migrate` now does that too.
- **`brief check` checks the block.** It reports YAML that doesn't parse, a missing `type`, `created` or `responsible-parties`, a `contributors` list that doesn't start with the creator, and a header line left beside the block.
- **`[brief] responsible_parties` names who a new top-level brief answers to.** Unset, it is the account's full name; a child brief copies its parent's list.
