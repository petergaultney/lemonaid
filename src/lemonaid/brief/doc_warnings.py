"""Vault documents mentioned as output should have a document subscription."""

import re
from collections import abc
from pathlib import Path

from . import doc_table, linked_asks, status


def warnings(text: str, vaults: abc.Collection[Path]) -> list[str]:
    parts = status.split(text)
    output = re.search(r"^## Output\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    mentioned = parts.now + (output[1] if output else "")
    cells = re.findall(r"\[[^\]]*\]\(<?[^>]+?>?\)", mentioned)
    listed = {row.path for row in doc_table.rows(text)}
    found = [
        (cell, path)
        for cell in cells
        if (path := doc_table.path_of(cell, vaults))
        and path.suffix == ".md"
        and any(path.is_relative_to(root.expanduser().resolve()) for root in vaults)
    ]
    return [
        *(
            f"{path} is linked but has no ### Docs row; use `brief doc add`"
            for path in dict.fromkeys(p for _cell, p in found)
            if path not in listed
        ),
        *(
            f"{path} has no heading `{heading}`, which a link here names"
            for cell, path in found
            if (heading := linked_asks.heading_of(doc_table.LINK.search(cell)["url"]))
            and _missing(path, heading)
        ),
    ]


def _missing(path: Path, heading: str) -> bool:
    try:
        return linked_asks.section(path.read_text(), heading) is None
    except OSError:
        return False  # an unreadable file is reported as missing elsewhere
