"""`place toss --dry-run` (and `--json` without `--yes`): what a toss would do, closing nothing."""

import json
import sys
import typing as ty

from . import escape, ownership, target, teardown, toss_warning, windows


class Preview(ty.NamedTuple):
    doomed: target.TossTarget | None
    refusals: list[str]
    warnings: list[str]
    clients: list[tuple[str, str]]

    @property
    def would_proceed(self) -> bool:
        return not self.refusals


def _label(place: ownership.Place) -> str:
    return f"{place.key} ({place.root.path})"


def build(
    doomed: target.TossTarget | None,
    why_not: str,
    editable_refusal: str,
    force: bool,
) -> Preview:
    if doomed is None:
        return Preview(None, [why_not], [], [])

    concerns = {place.directory: teardown.concerns(place) for place in doomed.places}
    moves, escape_error = escape.preview(doomed.session) if doomed.session else ([], "")
    window_moves, window_error = (
        windows.plan_client_moves(doomed.partial) if doomed.partial else ([], "")
    )

    return Preview(
        doomed,
        [
            *([editable_refusal] if editable_refusal else []),
            *(
                f"{_label(place)}: {reason}"
                for place in doomed.places
                for reason in concerns[place.directory]
                if not force
            ),
            *([escape_error] if escape_error else []),
            *([window_error] if window_error else []),
        ],
        [
            *(
                f"{name} ({state}) is awaiting action and will leave the inbox"
                for name, state in toss_warning.affected(doomed)
            ),
            *(
                f"client {client} is attached to {doomed.session!r} and would move to {dest!r}"
                for client, dest in moves
            ),
            *(
                f"client {client} is looking at a closing window and would move to {dest}"
                for client, dest in window_moves
            ),
        ],
        [*moves, *window_moves],
    )


_APPLY_HINT = "Nothing was closed. To apply this, run it again with --yes."
_JSON_NEEDS_YES = "--json does not confirm, so it only previews. Pass --yes to tear down."


def _report(preview: Preview) -> dict:
    doomed = preview.doomed

    return {
        "dry_run": True,
        "would_proceed": preview.would_proceed,
        "refusals": preview.refusals,
        "warnings": preview.warnings,
        "session": doomed.session if doomed else "",
        "released": [p.key for p in doomed.places] if doomed else [],
        "kept": list(doomed.kept) if doomed else [],
        "place": doomed.place.key if doomed and doomed.place else None,
        "closed_windows": doomed.closing if doomed else [],
        "session_closed": bool(doomed and doomed.session),
        "clients": [{"client": c, "moves_to": d} for c, d in preview.clients],
        "hint": _APPLY_HINT,
    }


def _verdict(preview: Preview) -> list[str]:
    if not preview.would_proceed:
        return ["A real toss would be refused. Nothing was closed."]

    return ["A real toss would proceed.", _APPLY_HINT]


def _lines(preview: Preview, describe: ty.Callable[[target.TossTarget], list[str]]) -> list[str]:
    return [
        *(describe(preview.doomed) if preview.doomed else []),
        *(f"warning: {w}" for w in preview.warnings),
        *(f"refused: {r}" for r in preview.refusals),
        *_verdict(preview),
    ]


def show(
    preview: Preview,
    as_json: bool,
    describe: ty.Callable[[target.TossTarget], list[str]],
    json_needs_yes: bool = False,
) -> ty.NoReturn:
    """Print the preview and exit; 2 when bare `--json` asked for a teardown it can't do."""
    if as_json:
        print(json.dumps(_report(preview)))
        print("\n".join(_verdict(preview)), file=sys.stderr)
    else:
        print("\n".join(_lines(preview, describe)))

    if json_needs_yes:
        print(f"error: {_JSON_NEEDS_YES}", file=sys.stderr)
        sys.exit(2)

    sys.exit(0 if preview.would_proceed else 1)
