"""Keep handoff inspection and launch off the inbox's event loop."""

import asyncio
import subprocess

from textual.app import App

from ....brief import identity, lemon
from ....brief.handoff import coordinator, launch, request, state
from ....config import Config
from ... import db
from .handoff_screens import HandoffConfirm, HandoffScreen


def _inspect(channel: str, config: Config) -> tuple[str, tuple[str, ...]]:
    if channel.partition(":")[0] not in ("claude", "codex"):
        raise ValueError("Handoff supports Claude and Codex lemons")

    with db.connect() as conn:
        attached = lemon.attachment(conn, channel, claim_pending=False)
        if attached.notification is None or attached.notification.is_archived:
            raise ValueError("Select a live lemon with an attached brief")
        source = identity.from_path(attached.path)
    names = dict.fromkeys(
        ("claude", "codex", *config.tmux_session.launch.presets, *config.tmux_session.templates)
    )
    destinations = []
    for name in names:
        try:
            launch.destination(name)
        except ValueError:
            continue
        destinations.append(name)
    return source, tuple(destinations)


def _start(channel: str, source: str, destination: str, recovery: bool) -> dict:
    with db.connect() as conn:
        attached = lemon.attachment(conn, source, claim_pending=False)
        if attached.channel != channel:
            raise ValueError("The selected lemon changed sessions; select it again")
        token, _, _ = request.prepare(conn, destination, source=channel, recover=recovery)
        try:
            report = coordinator.advance(conn, token)
        except (ValueError, LookupError, OSError, subprocess.SubprocessError):
            coordinator.recover_source(conn, state.get(conn, token), "failed")
            raise
        if report["phase"] not in ("complete", "failed"):
            request.watch(token)
        return report


def open_dialog(app: App, channel: str, config: Config) -> None:
    async def inspect() -> None:
        try:
            source, destinations = await asyncio.to_thread(_inspect, channel, config)
        except (ValueError, LookupError, OSError) as error:
            app.notify(str(error), severity="error")
            return

        def chosen(choice: tuple[str, bool] | None) -> None:
            if choice is None:
                return
            destination, recovery = choice

            async def execute() -> None:
                try:
                    report = await asyncio.to_thread(_start, channel, source, destination, recovery)
                except (ValueError, LookupError, OSError, subprocess.SubprocessError) as error:
                    app.notify(f"Handoff failed: {error}", severity="error", timeout=10)
                    return
                if report["phase"] == "failed":
                    app.notify(
                        "Handoff failed: " + "; ".join(report["missing"]),
                        severity="error",
                        timeout=10,
                    )
                    return

                app.notify(
                    f"Handoff {report['phase']}: {source} to {destination}. Token: {report['token']}",
                    timeout=10,
                )

            def confirmed(yes: bool) -> None:
                if yes:
                    app.run_worker(execute(), group="handoff")

            app.push_screen(HandoffConfirm(source, destination, recovery), confirmed)

        app.push_screen(HandoffScreen(source, destinations), chosen)

    app.run_worker(inspect(), group="handoff-inspect", exclusive=True)
