"""The inbox status line's text."""

from rich.markup import escape


def inbox_status(
    unread_count: int,
    read_count: int,
    current_env: str,
    search_matches: tuple[int, int] | None,
    unpatched: bool,
    drifted_dimension: str,
    save_size_key: str,
    arrange_error: str,
) -> str:
    """`search_matches` is (inbox, archive) while searching; `drifted_dimension` is empty
    unless the scratch pane's size has drifted from the saved one.
    """
    env_label = f" [{current_env}]" if current_env != "unknown" else ""
    text = f"{unread_count} unread, {read_count} read{env_label}"
    if search_matches is not None:
        inbox_count, archive_count = search_matches
        text = (
            f"{inbox_count} inbox match{'es' if inbox_count != 1 else ''} and "
            f"{archive_count} archive match{'es' if archive_count != 1 else ''}"
        )

    if unpatched:
        text += "  |  [bold cyan]P[/]atch Claude for faster notifications"

    if drifted_dimension:
        text += f"  |  [bold cyan]{save_size_key}[/] save pane {drifted_dimension} now"

    if arrange_error:
        text += f"  |  [bold red]arrange:[/] {escape(arrange_error)}"

    return text
