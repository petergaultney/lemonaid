import argparse

import pytest

from lemonaid.brief import cli, command


@pytest.fixture
def brief(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(tmp_path))
    path = tmp_path / "task.md"
    path.write_text(
        "# Task\n\nBrief-ID: IndexElf.task\nParent: IndexElf.lead\n\n"
        "## Now\n\nCurrent work.\n\n## Questions\n\n## Next\n\n- next step\n\n"
        "## Goal\n\nKeep this exactly.\n\n## Watching\n"
    )
    monkeypatch.setattr(command, "own_brief", lambda args: (path, ""))
    return path


@pytest.fixture
def run():
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())

    def invoke(*args):
        parsed = parser.parse_args(["brief", *args])
        parsed.func(parsed)

    return invoke
