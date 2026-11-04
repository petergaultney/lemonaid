from lemonaid.watch import pr_threads


def _thread(resolved: bool, *comments: tuple[str, str, str]) -> dict:
    return {
        "isResolved": resolved,
        "comments": {
            "nodes": [
                {"body": body, "state": state, "author": {"login": login}}
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
            ]
        }
    }

    assert pr_threads.unresolved(pr) == ("@sam", "Work", "Work")
