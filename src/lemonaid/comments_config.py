"""The `[comments]` table: the name your own review comments are signed with."""

import getpass
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CommentsConfig:
    author: str | None = None  # None signs with your login name

    def signature(self) -> str:
        """The author a comment you write in your editor gets. Set it to the name your
        Relay comments carry, so a thread names you the same way in code and in a vault."""
        return self.author or getpass.getuser()


def parse(data: object) -> CommentsConfig:
    if not isinstance(data, dict):
        print("Warning: [comments] must be a table", file=sys.stderr)
        return CommentsConfig()
    author = data.get("author")
    if author is not None and (not isinstance(author, str) or not author.strip()):
        print("Warning: [comments] author must be a non-empty string", file=sys.stderr)
        author = None
    return CommentsConfig(author=author)
