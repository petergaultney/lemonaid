"""Vault documents mentioned as output should have a document subscription."""

import re
from collections import abc
from pathlib import Path

from . import doc_table, status


def warnings(text: str, vaults: abc.Collection[Path]) -> list[str]:
    parts = status.split(text)
    output = re.search(r"^## Output\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    mentioned = parts.now + (output[1] if output else "")
    cells = re.findall(r"\[[^\]]*\]\(<?[^>]+?>?\)", mentioned)
    listed = {row.path for row in doc_table.rows(text)}
    return [
        f"{path} is linked but has no ### Docs row; use `brief doc add`"
        for cell in cells
        if (path := doc_table.path_of(cell, vaults))
        and path.suffix == ".md"
        and any(path.is_relative_to(root.expanduser().resolve()) for root in vaults)
        and path not in listed
    ]
