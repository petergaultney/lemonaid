from lemonaid.brief import doc_table, now_edit, pr_table, store
from lemonaid.inbox import db
from lemonaid.tasks.briefs import subject_hints

from ..shared import new_task

_PR = "https://github.com/acme/widgets/pull/7"
_BRIEF = "---\ntype: Brief\nbrief-id: Work.alpha\n---\n# Work\n\n## Now\n\nWorking.\n\n## Goal\n"


def _registered(tmp_path):
    path = store.briefs_dir() / "work.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_BRIEF)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lemon_identities (lemon_id, path) VALUES ('Work.alpha', ?)", (str(path),)
        )
        conn.commit()
    return path


def _unwatched(*urls: str) -> list[str]:
    with db.connect() as conn:
        return [subject_hints.unwatched(conn, "brief:Work.alpha", url) for url in urls]


def test_a_pr_or_file_the_holder_doesnt_watch_gets_the_command_that_would(tmp_path):
    path, doc = _registered(tmp_path), (tmp_path / "design.md").resolve()
    urls = (_PR, doc.as_uri(), "https://example.com/x")

    unlisted = _unwatched(*urls)
    path.write_text(
        now_edit.with_section(
            doc_table.add(_BRIEF, doc, "Design"),
            "PRs",
            lambda body: pr_table.with_row(body, _PR, "Work", None),
        )
    )
    listed = _unwatched(*urls)

    assert f"`lemonaid brief pr add --self {_PR} WORK`" in unlisted[0]
    assert f"`lemonaid brief doc add --self {doc} PURPOSE`" in unlisted[1]
    assert unlisted[2] == "" and listed == ["", "", ""]


def test_a_brief_with_a_task_that_has_no_url_is_hinted_to_set_it(tmp_path):
    path = _registered(tmp_path)
    with db.connect() as conn:
        made = new_task(conn)

    bare = subject_hints.for_brief(path, _PR)
    with db.connect() as conn:
        new_task(conn, request_id="carrier", subject_url_text=_PR + "/")
    carried = subject_hints.for_brief(path, _PR)

    assert f"`lemonaid task set-url {made} {_PR} --reason TEXT`" in bare
    assert carried == ""


def test_a_brief_with_no_tasks_or_no_lemon_id_gets_no_hint(tmp_path):
    path = _registered(tmp_path)
    stranger = tmp_path / "stranger.md"
    stranger.write_text("# Stranger\n")

    assert subject_hints.for_brief(path, _PR) == ""
    assert subject_hints.for_brief(stranger, _PR) == ""
