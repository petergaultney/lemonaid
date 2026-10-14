# Minor

#### Changed

- **Each PR describes its change in a file under `changes/` instead of bumping the version and editing `CHANGES.md`, so merging PRs no longer conflicts on either.** The file's first line says whether it needs a patch, minor or major release.
- **Merging a PR no longer publishes a release.** A workflow releases daily and on demand: it tags the newest tested commit with the next version, taken from the change files added since the previous tag, and publishes that tag's build with those files as its notes.
- **`pyproject.toml` has no version; the build takes it from the tag.** A build between releases gets a dev version such as `0.116.1.dev3+g1a2b3c4`.
