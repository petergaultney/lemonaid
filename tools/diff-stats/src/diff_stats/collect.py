"""Aggregate file-level and Python line-level diff statistics."""

from collections import abc

from . import python_lines


def collect_categories(
    base: str,
    numstats: abc.Iterable[tuple[str, int, int]],
    categorize: abc.Callable[[str], str],
    category_names: abc.Iterable[str],
) -> tuple[dict[str, dict], list[str]]:
    numstats = tuple(numstats)
    python_stats, warnings = python_lines.classify_python_diff(
        base,
        {
            filepath: (added, removed)
            for filepath, added, removed in numstats
            if categorize(filepath) == "code" and filepath.endswith(".py")
        },
    )
    categories: dict[str, dict] = {
        name: {"files": [], "added": 0, "removed": 0} for name in category_names
    }

    for filepath, added, removed in numstats:
        split_stats = python_stats.get(filepath)
        if not split_stats:
            category = categorize(filepath)
            categories[category]["files"].append(filepath)
            categories[category]["added"] += added
            categories[category]["removed"] += removed
            continue

        classified = False
        for category, (category_added, category_removed) in split_stats.items():
            if not category_added and not category_removed:
                continue

            classified = True
            categories[category]["files"].append(filepath)
            categories[category]["added"] += category_added
            categories[category]["removed"] += category_removed

        if not classified:
            categories["code"]["files"].append(filepath)

    return categories, warnings
