# Minor

#### Added

- **Briefs support arbitrary heading edits.** `brief section show|set|rm` and `brief bullet add|set|rm` work by heading name, and refuse ambiguous matches.
- **Next, PRs, Docs and Done have their own sections.** Readers accept both layouts; `brief migrate --self` or `--all` explicitly promotes legacy headings, and `brief check` warns when migration is available.
