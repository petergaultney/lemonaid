# Minor

#### Added

- **A lemon can stand on another lemon's tree in the grove, wherever it runs.** Press `t` in select mode, choose **To another lemon's tree** in the grove window's menu, or run `lemonaid grove graft LEMON --onto LEMON`; `grove ungraft`, or **back to its own tree** in `t`'s list, undoes it.
- **A graft is kept in lemonaid's database by Lemon-ID,** so it holds across restarts, resumes and renamed trees, and while its host isn't live the lemon stands on its own tree. `grove grafts` lists them, and `grove show --json` gives each lemon's `grafted_onto`.

#### Fixed

- The grove window's edit menu takes an edit's letter with Shift held or Caps Lock on, as its labels show the letter capitalized.
