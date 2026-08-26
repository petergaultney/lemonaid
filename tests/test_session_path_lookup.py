"""Finding a session's transcript when the cwd does not name its directory.

Claude derives its own project directory name, and the derivation does not
round-trip for every path. A session whose transcript is never found gets no
message updates at all, which in the inbox reads as a session that went quiet
rather than one nobody can see.
"""

from lemonaid.claude import watcher


def test_the_recorded_path_wins(tmp_path, monkeypatch):
    """Claude reports the transcript in every hook payload; trust it."""
    recorded = tmp_path / "somewhere" / "abc.jsonl"
    recorded.parent.mkdir(parents=True)
    recorded.write_text("{}\n")

    assert watcher.get_session_path("abc", "/any/cwd", str(recorded)) == recorded


def test_a_recorded_path_that_no_longer_exists_is_not_used(tmp_path):
    gone = str(tmp_path / "gone.jsonl")

    assert watcher.get_session_path("abc", "", gone) is None


def test_the_cwd_derivation_still_works(tmp_path, monkeypatch):
    project = tmp_path / "-tmp-proj"
    project.mkdir()
    (project / "sid1.jsonl").write_text("{}\n")

    monkeypatch.setattr(
        "lemonaid.claude.projects.find_project_path",
        lambda cwd: project if cwd == "/tmp/proj" else None,
    )

    assert watcher.get_session_path("sid1", "/tmp/proj") == project / "sid1.jsonl"


def test_a_session_id_lookup_rescues_a_cwd_that_does_not_derive(tmp_path, monkeypatch):
    """The inbox's cwd and the cwd Claude filed the session under can differ."""
    project = tmp_path / "-real-dir"
    project.mkdir()
    (project / "sid2.jsonl").write_text("{}\n")

    monkeypatch.setattr(
        "lemonaid.claude.projects.find_project_path",
        lambda cwd: project if cwd == "/real/dir" else None,
    )
    monkeypatch.setattr(
        "lemonaid.claude.projects.find_session_project",
        lambda session_id: "/real/dir" if session_id == "sid2" else None,
    )

    assert watcher.get_session_path("sid2", "/what/the/inbox/recorded") == project / "sid2.jsonl"


def test_no_session_id_is_not_a_lookup(tmp_path):
    assert watcher.get_session_path("", "/tmp/proj") is None
