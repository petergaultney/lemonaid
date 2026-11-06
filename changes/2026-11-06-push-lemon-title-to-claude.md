# Minor

#### Added

- **A Claude lemon's session title is `<emoji> <name> (<WordyBin>)`, set from lemonaid.** The `UserPromptSubmit` hook (`lemonaid claude submit`) renames the Claude session when its title differs, so the name shows that way in Claude's remote session list. It runs on prompt submit only, and lemonaid always wins over a rename made in Claude. A session with neither an emoji nor a brief keeps its own title.
