#!/usr/bin/env python3
"""Print the next release's version or notes from the change files added since a tag.

    scripts/release.py version [--since v0.115.3] [--until HEAD]
    scripts/release.py notes [--since v0.115.3] [--until HEAD]
    scripts/release.py latest [--below 0.116.0]

`--since` defaults to the highest `v*` tag. The version is that tag's raised by the
highest bump among the files added to changes/ between the two revisions, and the notes
are those files' entries in date order. `latest` prints the highest `v*` tag's version,
or the highest below a version. Changes nothing. Exits 2 when no change files were added
and 1 when one is malformed. The release workflow (.github/workflows/release.yml) runs it.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import changefiles


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _added_changes(root: Path, since: str, until: str) -> dict[str, str]:
    paths = _git(
        root,
        "diff",
        "-z",
        "--no-renames",
        "--diff-filter=A",
        "--name-only",
        since,
        until,
        "--",
        "changes/",
    ).split("\0")
    return {
        Path(path).name: _git(root, "show", f"{until}:{path}")
        for path in paths
        if path and Path(path).name != changefiles.README
    }


def _tag_versions(root: Path, below: str) -> list[str]:
    tags = _git(root, "tag", "--list", "v*").split()
    if not below:
        return tags

    return [
        t
        for t in tags
        if changefiles.is_version(t)
        and changefiles.parse_version(t) < changefiles.parse_version(below)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("what", choices=["version", "notes", "latest"])
    parser.add_argument("--since", help="the previous release's tag (default: the highest v*)")
    parser.add_argument("--until", default="HEAD", help="the revision to release")
    parser.add_argument("--below", default="", help="for `latest`: the version to stay under")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent, help="the repo"
    )
    args = parser.parse_args(argv)

    root: Path = args.root
    if args.what == "latest":
        print(changefiles.latest_version(_tag_versions(root, args.below)))
        return 0

    since = args.since or "v" + changefiles.latest_version(_tag_versions(root, ""))
    changes = _added_changes(root, since, args.until)
    try:
        if args.what == "version":
            print(changefiles.next_version(changes, since))
        else:
            sys.stdout.write(changefiles.release_notes(changes))
    except changefiles.NothingToRelease as err:
        print(f"{err} ({since})", file=sys.stderr)
        return 2

    except changefiles.MalformedChange as err:
        print(err, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
