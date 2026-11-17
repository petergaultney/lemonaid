from lemonaid.watch import scout_failures


def test_retries_wait_longer_with_each_failure_in_a_row_until_cleared():
    assert scout_failures.delay("task.IndexElf", 30) == 30
    first = scout_failures.record("task.IndexElf", "one")
    assert scout_failures.failing("task.IndexElf") is None

    for _ in range(9):
        scout_failures.record("task.IndexElf", "again")

    assert scout_failures.failing("task.IndexElf") == ("again", 10, first.since)
    assert scout_failures.delay("task.IndexElf", 30) == 600
    scout_failures.clear("task.IndexElf")
    assert scout_failures.delay("task.IndexElf", 30) == 30
