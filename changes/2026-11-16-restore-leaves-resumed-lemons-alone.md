# Patch

`lemonaid restore` no longer starts a lemon a second time when someone brings it back while the restore runs. Just before starting each lemon it checks, under a start lock that `lemon resume` and `tell`'s autoresume also take, whether the lemon came back meanwhile, and reports it `already running` instead of failing with "index in use" or opening a second copy of the conversation.

While a restore runs, `lemon resume` refuses a lemon lost with its terminal, `tell` leaves it to the restore, and `watch` holds back `gone` and `exited` reports for it, so a parent isn't prompted to resume its children alongside the restore.

Attaching a lost lemon's brief to a new conversation archives the lost row as `replaced`, so restore stops proposing the old one. Each restore and each lemon it starts is recorded in `lemonaid audit`.
