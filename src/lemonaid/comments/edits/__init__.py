"""The text edits that add a comment, reply, resolve, or strip every comment from a file.

Each command takes the file's current text and returns edits against it, so the server
can send them to an editor as a `WorkspaceEdit` and the CLI can apply them to the file.
Records are only ever appended. Inserted lines use the file's line ending.
"""

from ..model import Edit
from ._edit import Added, apply
from ._write import encode, new_id, now
from .add import add_comment
from .reply import reply
from .resolve import resolve
from .strip import strip

__all__ = [
    "Added",
    "Edit",
    "add_comment",
    "apply",
    "encode",
    "new_id",
    "now",
    "reply",
    "resolve",
    "strip",
]
