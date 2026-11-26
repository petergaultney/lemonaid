# Minor

#### Added

- **The grove window works on a phone,** in `grove serve`: a tap on a lemon chooses it, a drag only pans, a tap on a tree with more than one lemon opens it full screen with a row for each, and the back button backs out.

#### Changed

- **The grove's packhouse is off unless you turn it on.** Lemons in no group are an ordinary block `0` at the grove's middle, where the roads meet, and the groups gather around it; set `grove_packhouse = true` under `[tui]` to stand them in the packhouse again, as suits a grove with many of them. Each way keeps its own layout, so switching back puts everything where it was.
