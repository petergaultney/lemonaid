from lemonaid.watch import pr_threads


def _thread(resolved: bool, *comments: tuple[str, str, str]) -> dict:
    return {
        "isResolved": resolved,
        "comments": {
            "nodes": [
                {
                    "body": body,
                    "state": state,
                    "author": {"login": login},
                    "viewerDidAuthor": login == "me",
                }
                for login, body, state in comments
            ]
        },
    }


def test_each_unresolved_thread_names_who_spoke_last_in_it():
    pr = {
        "reviewThreads": {
            "nodes": [
                _thread(False, ("sam", "please fix", "SUBMITTED")),
                _thread(False, ("sam", "fix", "SUBMITTED"), ("me", "🍋 Work (Author): done", "")),
                _thread(False, ("me", "🍋 Work (Author): ok", ""), ("me", "draft", "PENDING")),
                _thread(True, ("sam", "fix", "SUBMITTED")),
                _thread(False, ("sam", "draft", "PENDING")),
                _thread(False, ("sam", "fix", "SUBMITTED"), ("me", "fixed", "")),
            ]
        }
    }

    assert pr_threads.unresolved(pr) == (
        "other sam", "user me Work", "user me Work", "user me"
    )  # fmt: skip


def test_threads_from_a_snapshot_that_didnt_ask_whose_account_wrote_them_arent_known():
    thread = _thread(False, ("sam", "fix", "SUBMITTED"))
    del thread["comments"]["nodes"][0]["viewerDidAuthor"]

    assert pr_threads.unresolved({"reviewThreads": {"nodes": [thread]}}) is None
