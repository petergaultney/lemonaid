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


def test_a_check_finishing_while_others_run_leaves_the_fingerprint_alone(monkeypatch):
    def pr(rollup_state, checks):
        contexts = {"totalCount": len(checks), "nodes": checks}
        rollup = {"state": rollup_state, "contexts": contexts}
        return {"r0": {"p1": {"commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]}}}}

    running = {"status": "IN_PROGRESS", "conclusion": None, "completedAt": None}
    passed = {"status": "COMPLETED", "conclusion": "SUCCESS", "completedAt": "2026-11-05T22:00:00Z"}
    replies = [
        pr("PENDING", [running, running]),
        pr("PENDING", [passed, running]),
        pr("SUCCESS", [passed, passed]),
    ]
    monkeypatch.setattr(github_api, "graphql", lambda *args, **kwargs: replies.pop(0))

    first, second, done = (pr_changes.fingerprints([("a/x", 1)])[("a/x", 1)] for _ in range(3))

    assert first == second != done


def test_a_batch_github_refuses_is_read_again_in_halves(monkeypatch):
    sizes = []

    def graphql(fields, query, *, partial=False):
        sizes.append(query.count("pullRequest("))
        if sizes[-1] > pr_changes._BATCH // 2:
            return None
        return {"r0": {f"p{n}": {"state": "OPEN"} for n in range(pr_changes._BATCH)}}

    monkeypatch.setattr(github_api, "graphql", graphql)

    found = pr_changes.fingerprints(("o/r", n) for n in range(pr_changes._BATCH))

    assert len(found) == pr_changes._BATCH
    assert sizes == [pr_changes._BATCH, pr_changes._BATCH // 2, pr_changes._BATCH // 2]
