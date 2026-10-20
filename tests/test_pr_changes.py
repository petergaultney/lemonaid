from lemonaid.watch import github_api, pr_changes


def test_one_query_covers_many_repos_and_skips_an_unreadable_pr(monkeypatch):
    queries = []

    def graphql(fields, query, *, partial=False):
        queries.append((query, partial))
        return {
            "r0": {"p1": {"state": "OPEN"}, "p2": None},
            "r1": {"p7": {"state": "MERGED"}},
        }

    monkeypatch.setattr(github_api, "graphql", graphql)

    found = pr_changes.fingerprints([("a/x", 2), ("a/x", 1), ("b/y", 7), ("a/x", 1)])

    assert set(found) == {("a/x", 1), ("b/y", 7)}
    assert found[("a/x", 1)] != found[("b/y", 7)]
    [(query, partial)] = queries
    assert partial
    assert (
        'r0: repository(owner: "a", name: "x")' in query and "p2: pullRequest(number: 2)" in query
    )


def test_many_prs_are_read_in_batches(monkeypatch):
    calls = []
    monkeypatch.setattr(github_api, "graphql", lambda *args, **kwargs: calls.append(1) or {})

    assert pr_changes.fingerprints(("o/r", n) for n in range(pr_changes._BATCH + 1)) == {}
    assert len(calls) == 2


def test_no_prs_means_no_query(monkeypatch):
    monkeypatch.setattr(github_api, "graphql", lambda *args, **kwargs: 1 / 0)

    assert pr_changes.fingerprints([]) == {}


def test_a_new_running_check_changes_the_fingerprint_though_the_rollup_stays_failed(monkeypatch):
    failed = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
    running = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": None}

    def pr(checks):
        rollup = {"state": "FAILURE", "contexts": {"totalCount": len(checks), "nodes": checks}}
        return {"r0": {"p1": {"commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]}}}}

    replies = [pr([failed]), pr([failed, running])]
    monkeypatch.setattr(github_api, "graphql", lambda *args, **kwargs: replies.pop(0))

    before, after = (pr_changes.fingerprints([("a/x", 1)]) for _ in range(2))

    assert before[("a/x", 1)] != after[("a/x", 1)]
