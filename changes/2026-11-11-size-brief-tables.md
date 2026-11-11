# Patch

- **The brief view's PRs and Docs tables size their columns to their content.** A short column such as the PR link fits its text and never truncates, an absolute path shows its file name (the full path is in its tooltip), and the longest text column takes the remaining width and wraps at word boundaries. No column is squeezed below about 12 characters of text (or all its text, if it has less; a column of 20 characters or fewer is never narrowed); in a view too narrow for that, the table is wider than the view.
