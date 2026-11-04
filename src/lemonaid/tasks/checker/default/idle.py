"""The default checker's last resort: a holder idle past its grace with nothing to wait on
is asked who moves next."""

from .. import checker_input, protocol
from . import settings


def _ask(task_id: str) -> str:
    return "\n".join(
        [
            "You are idle holding this task. Who moves next?",
            "- You: act on it.",
            "- Another lemon: hand it this task, since it must act on your result:"
            f" `lemonaid task assign {task_id} --to BRIEF --reason TEXT`. If that lemon holds a"
            " task of its own for what you wait on, wait for that one instead:"
            f" `lemonaid task depend {task_id} --on OTHER_TASK_ID`. A Status never waits on a"
            " lemon.",
            "- A person or a process: keep the task and set your brief's Status to say which:"
            " `blocked` for your user, `merge` when only your user's merge remains, `approve`"
            " for your user's approval, `review` for a teammate's review, `running` while a long"
            " process runs. A Status covers every task you hold.",
            "- CI on the task's PR: give the task its PR, and the inspector waits while CI runs:"
            f" `lemonaid task set-url {task_id} PR_URL --reason TEXT`.",
            "- Nobody, because the work is finished: close it, naming where the result is:"
            f" `lemonaid task close {task_id} --reason TEXT`.",
            "- Another lemon's task already covers this work: follow that one instead:"
            f" `lemonaid task observe OTHER_TASK_ID --instead-of {task_id}`.",
        ]
    )


def challenge(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    return [
        (
            "challenge",
            view.subject,
            "progress",
            view.fields["revision"],
            "brief",
            brief,
            _ask(view.subject),
        )
    ]
