# Patch

#### Fixed

- **Archiving moves only a brief its database records.** A run with `LEMONAID_DB` pointed at another database, but with the real briefs, used to treat every brief as unused. Its daily sweep could then move live lemons' briefs to the attic, and write the audit records into its own state directory.
