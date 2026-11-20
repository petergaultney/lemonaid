import plistlib

from lemonaid.slack import bundle


def test_the_bundle_names_lemonaid_and_runs_the_given_python(tmp_path):
    executable = bundle.ensure(tmp_path, "/opt/my python/bin/python3")

    info = plistlib.loads((executable.parent.parent / "Info.plist").read_bytes())
    assert (info["CFBundleName"], info["CFBundleExecutable"]) == ("lemonaid", "lemonaid")
    assert executable.stat().st_mode & 0o111
    lines = executable.read_text().splitlines()
    assert lines[1] == 'export CFProcessPath="$0"'
    assert lines[2] == "exec '/opt/my python/bin/python3' -P -m lemonaid slack window \"$@\""


def test_ensuring_it_again_leaves_it_alone(tmp_path):
    executable = bundle.ensure(tmp_path, "/usr/bin/python3")
    before = executable.stat().st_mtime_ns

    bundle.ensure(tmp_path, "/usr/bin/python3")

    assert executable.stat().st_mtime_ns == before
