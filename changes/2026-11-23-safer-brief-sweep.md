# Minor

#### Fixed

- **Archiving moves only a brief its database records.** A run with `LEMONAID_DB` pointed at another database, but with the real briefs, used to treat every brief as unused. Its daily sweep could then move live lemons' briefs to the attic, and write the audit records into its own state directory.

#### Changed

- **lemonaid won't run with only part of its storage redirected.** When some of the database, the state directory, the briefs and the mailboxes point away from their defaults and others don't, every `lemonaid` and `lma` command exits and names each with its path.
- **Only the scout host starts the daily brief sweep.** Any lemonaid command used to start it, harness hooks included, and two could start it at once.
