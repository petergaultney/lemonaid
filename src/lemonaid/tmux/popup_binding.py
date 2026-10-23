"""A tmux.conf binding for a fast popup, in tmux commands alone, so pressing it starts no Python."""

from . import fast_popup


def binding(name: str, key: str, margin: int, title: str) -> str:
    """A tmux.conf `bind-key` that shows popup *name* without starting Python, closing it on any
    other client first, and closes it when pressed inside it; only when the resident isn't running
    does it fall back to `tmux popup`.
    """
    session = fast_popup.session_for(name)
    # run-shell -C expands the formats, which display-popup's -w and -h don't, then runs it.
    popup = (
        " ".join(
            [
                "display-popup -E",
                f"-w #{{e|-:#{{client_width}},{2 * margin}}}",
                f"-h #{{e|-:#{{client_height}},{2 * margin}}}",
                f"-x {margin} -y #{{e|-:#{{client_height}},{margin}}}",  # -y is its bottom line
                "-S fg=##f2d94e",
                f"-T '{title}'",
                *(f"'{arg}'" for arg in fast_popup.attach_command(name)),
            ]
        )
        .replace('"', '\\"')
        .replace("$", "\\$")
    )
    return "\n".join(
        [
            f"bind-key {key} {{",
            f"  if-shell -F '#{{==:#{{session_name}},{session}}}' {{ detach-client }} {{",
            f"    if-shell -F '#{{S:#{{?#{{==:#{{session_name}},{session}}},1,}}}}' {{",
            f"      if-shell -F -t ={session}: '#{{session_attached}}' {{ detach-client -s ={session} }}",
            f"      set-option -F -t ={session}: {fast_popup.OPENER_OPTION} '#{{client_name}}'",
            f'      run-shell -C "{popup}"',
            "    } {",
            f"      run-shell -b 'lemonaid tmux popup {name}'",
            "    }",
            "  }",
            "}",
        ]
    )
