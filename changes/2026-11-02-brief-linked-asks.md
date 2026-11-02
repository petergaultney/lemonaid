# Minor

#### Added

- **A `Needs` bullet can link to a Markdown heading, and that section is its entry.** `brief show` and the inbox brief view show the section where they show a `## Questions` entry, and the answer keys work on it; a `## Questions` entry for the same bullet wins. `brief check` now ignores the `#heading` when matching a linked file to `### Docs` rows, and warns when the heading does not exist.
