"""`lemonaid slack`: sign in to Slack for your lemons, and see or remove that sign-in."""

import argparse
import subprocess
import sys
import time

from ..config import load_config
from . import bundle, gateway_socket, session, signed_out, wakes

_EXTRA = "uv tool install 'lemonaid-inbox[slack]'"


def _cmd_signin(args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        sys.exit("Slack sign-in runs on macOS only, for now")

    saved = session.load()
    workspace = args.workspace or load_config().slack.workspace or (saved.api_url if saved else "")
    if not workspace:
        sys.exit(
            "Name your Slack workspace: lemonaid slack signin https://<name>.slack.com/"
            " (or set workspace under [slack] in the config)"
        )
    executable = bundle.ensure(wakes.state_dir(), sys.executable)
    sys.exit(subprocess.run([str(executable), workspace]).returncode)


def _cmd_window(args: argparse.Namespace) -> None:
    try:
        # Optional: pywebview and PyObjC come with the `slack` extra, not with lemonaid itself.
        from . import window
    except ImportError as error:
        sys.exit(f"Slack sign-in needs the slack extra ({error.name} is missing): {_EXTRA}")
    sys.exit(window.run(args.workspace))


def _cmd_status(_args: argparse.Namespace) -> None:
    current = session.load()
    if current is None:
        sys.exit(f"Not signed in to Slack; {signed_out.SIGN_IN}")

    age = (time.time() - current.captured_at) / 86400
    print(
        f"Signed in to Slack as {current.user} ({current.user_id}) on {current.team},"
        f" {age:.0f} days ago; the session's cookie expires {current.cookie_expires or '(unknown)'}"
    )
    if problem := signed_out.problem(current):
        print(problem)
    settings = load_config().slack
    socket = (
        f"off ([slack] push = false); each is fetched every {settings.fetch_every:g}s"
        if not settings.push
        else f"not installed ({_EXTRA}); each is fetched every {settings.fetch_every:g}s"
        if not gateway_socket.available()
        else "up"
        if wakes.gateway_up()
        else "down"
    )
    print(f"Socket: {socket}; {len(wakes.followed(time.time()))} thread(s) or channel(s) followed")


def _cmd_signout(_args: argparse.Namespace) -> None:
    if not session.delete():
        print("lemonaid had no Slack session")
        return

    print(
        "Removed lemonaid's Slack session from the Keychain. Slack still lists it among your"
        " sessions until it expires; sign it out there to end it now."
    )


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("slack", help="Sign in to Slack so lemons can follow threads")
    commands = parser.add_subparsers(
        dest="slack_command", required=True, metavar="{signin,status,signout}"
    )
    signin = commands.add_parser(
        "signin",
        help="Open lemonaid's sign-in window and keep the session in the Keychain (macOS)",
    )
    signin.add_argument(
        "workspace",
        nargs="?",
        default="",
        help="Your workspace's URL, such as https://acme.slack.com/",
    )
    signin.set_defaults(func=_cmd_signin)
    window = commands.add_parser("window")  # run by the Lemonaid.app bundle; unlisted in --help
    window.add_argument("workspace")
    window.set_defaults(func=_cmd_window)
    commands.add_parser("status", help="Who lemonaid reads Slack as, and its socket").set_defaults(
        func=_cmd_status
    )
    commands.add_parser(
        "signout", help="Remove lemonaid's Slack session from the Keychain"
    ).set_defaults(func=_cmd_signout)
