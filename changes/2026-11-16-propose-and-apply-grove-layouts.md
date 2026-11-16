# Minor

#### Added

- **A lemon can garden your grove blocks in a proposed layout before applying it.** `grove propose FILE` copies the live layout, `--layout FILE` makes `show`, `move`, `resize`, `reshape`, `clear-open` and the new `plant` (which stands one tree) draw and change that file, and `grove apply FILE` gives the live grove its block plots and tree spots in one step. `plant` and `apply` refuse a tree off its block's ground or on another tree, and a lead moved farther from the packhouse.
- **`grove show --json` lists warnings** about what looks off: tags bumping into neighboring trees in the grove view, trees past their block's edge or off its ground, leads not nearest the packhouse, and lemon lists drawn away from their trees zoomed in. Zoomed `grove show N` names those lists on stderr too.

#### Fixed

- **`grove reshape` refuses corners squared onto a road or the stream, or rounded out from under a tree,** as `move` and `resize` refuse a road.
