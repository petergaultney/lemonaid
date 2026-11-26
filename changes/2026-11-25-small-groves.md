# Minor

#### Added

- **A home group can be block 0,** along with the lemons in no group, under its own name and color: `lemonaid grove home <group>`, or a block's menu in the grove window. The window's block menu also gives a group an earlier or later number, as moving its header does in the inbox.

- **The grove window works on a phone,** in `grove serve`: a tap on a lemon chooses it, a drag only pans, a tap on a tree with more than one lemon opens it full screen with a row for each, and the back button backs out.

- **The grove's blocks can be numbered from 1:** `grove_first_block = 1` under `[tui]` makes the lemons in no group block 1, and the groups follow from 2.

#### Changed

- **The grove's packhouse is off unless you turn it on.** Lemons in no group are an ordinary block `0` at the grove's middle, where the roads meet, and the groups gather around it; set `grove_packhouse = true` under `[tui]` to stand them in the packhouse again, as suits a grove with many of them. Each way keeps its own layout, so switching back puts everything where it was.
