def table(*numbers: int) -> str:
    return "## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n" + "".join(
        f"| task | [repo#{n}](https://github.com/owner/repo/pull/{n}) | |\n" for n in numbers
    )
