from lemonaid.resume_directory import surviving_directory


def test_uses_nearest_surviving_parent_without_recreating_the_directory(tmp_path):
    removed = tmp_path / "gone" / "child"
    assert surviving_directory(str(removed)) == str(tmp_path)
    assert not removed.exists()


def test_existing_directory_is_preserved(tmp_path):
    assert surviving_directory(str(tmp_path)) == str(tmp_path)
