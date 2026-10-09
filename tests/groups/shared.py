import argparse
import contextlib
import json

import lemonaid.groups.cli
import lemonaid.lineage.cli


def run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    lemonaid.groups.cli.setup_parser(subparsers)
    lemonaid.lineage.cli.setup_parser(subparsers)
    args = parser.parse_args(argv)
    with contextlib.suppress(SystemExit):
        args.func(args)

    out = capsys.readouterr()
    return json.loads(out.out) if "--json" in argv else {"out": out.out, "err": out.err}


def members(result: dict) -> list[str]:
    return [m["lemon_id"] for m in result["group"]["members"]]
