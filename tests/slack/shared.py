"""A fake Keychain (`security`) and a fake Slack Web API for the Slack tests."""

import dataclasses
import itertools
import subprocess

from lemonaid.slack import api, permalink, session

TOKEN = "xoxc-1111-secret-token"
COOKIE = "secret%2Fcookie"
SESSION = session.Session(
    api_url="https://acme.slack.com/",
    user_id="U0SAM",
    user="sam",
    team="Acme",
    token=TOKEN,
    cookie=COOKIE,
    cookie_expires="2027-12-25",
    team_id="T0ACME",
    captured_at=1000.0,
)
THREAD = permalink.Conversation("acme.slack.com", "C0TEAM", "1794857970.806329")
LINK = THREAD.link
CHANNEL = permalink.Conversation("acme.slack.com", "C0TEAM", "")


class Keychain:
    """`security` with one generic-password store; `argv` keeps every invocation's arguments."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.argv: list[list[str]] = []

    def __call__(self, args: list[str], stdin: str = "") -> subprocess.CompletedProcess:
        self.argv.append(args)
        if args == ["-i"]:
            words = stdin.split()
            option = {k: v for k, v in itertools.pairwise(words) if k.startswith("-")}
            self.items[option["-s"], option["-a"]] = bytes.fromhex(option["-X"]).decode()
            return subprocess.CompletedProcess(args, 0, "", "")

        key = (args[args.index("-s") + 1], args[args.index("-a") + 1])
        if key not in self.items:
            return subprocess.CompletedProcess(args, 44, "", "not found")

        if args[0] == "delete-generic-password":
            del self.items[key]
            return subprocess.CompletedProcess(args, 0, "", "")

        return subprocess.CompletedProcess(args, 0, self.items[key] + "\n", "")


def reply(ts: str, text: str, user: str = "U0ANN") -> dict:
    return {"ts": ts, "thread_ts": THREAD.ts, "user": user, "text": text}


def post(ts: str, text: str, user: str = "U0ANN", **more: str) -> dict:
    return {"ts": ts, "user": user, "text": text, **more}


def _newer(messages: list[dict], params: dict) -> list[dict]:
    oldest = permalink.order(params.get("oldest", "0"))
    return [m for m in messages if permalink.order(m["ts"]) > oldest]


@dataclasses.dataclass
class Slack:
    """`api.call` over one thread's replies and its channel's posts; set `error` to make every
    call raise it."""

    replies: list[dict] = dataclasses.field(default_factory=list)
    posts: list[dict] = dataclasses.field(default_factory=list)
    names: dict[str, str] = dataclasses.field(default_factory=lambda: {"U0ANN": "Ann"})
    calls: list[tuple[str, dict]] = dataclasses.field(default_factory=list)
    error: Exception | None = None

    def __call__(self, current: session.Session, method: str, **params: str) -> dict:
        assert method in api.READ_METHODS
        self.calls.append((method, params))
        if self.error:
            raise self.error

        if method == "users.info":
            return {"ok": True, "user": {"profile": {"display_name": self.names[params["user"]]}}}

        if method == "conversations.history":
            newest_first = list(reversed(_newer(self.posts, params)))
            if params.get("limit") == "1":
                return {"ok": True, "messages": newest_first[:1], "has_more": len(self.posts) > 1}
            return {"ok": True, "messages": newest_first, "has_more": False}

        latest = self.replies[-1]["ts"] if self.replies else None
        root = {"ts": THREAD.ts, **({"latest_reply": latest} if latest else {})}
        if params.get("limit") == "1":
            return {"ok": True, "messages": [root], "has_more": bool(self.replies)}

        return {"ok": True, "messages": [root, *_newer(self.replies, params)], "has_more": False}

    def fetches(self) -> int:
        reads = ("conversations.replies", "conversations.history")
        return sum(1 for method, _ in self.calls if method in reads)
