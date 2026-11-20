import subprocess
import time

from lemonaid import go


def test_a_control_mode_client_is_not_a_terminal_to_jump(tmp_path):
    socket = f"lma-go-client-{time.monotonic_ns()}"
    command = ["tmux", "-L", socket]
    subprocess.run([*command, "-f", "/dev/null", "new-session", "-d", "-s", "work"], check=True)
    control = subprocess.Popen(
        [*command, "-C", "attach", "-t", "work"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            listed = subprocess.run(
                [*command, "list-clients", "-F", "#{client_name}"], capture_output=True, text=True
            ).stdout
            if listed.strip():
                break

            time.sleep(0.05)
        assert listed.strip(), "control client never attached"

        try:
            go._client(command, "", "")
        except LookupError as error:
            assert "found none" in str(error)
        else:
            raise AssertionError("a control-mode client was chosen")
    finally:
        control.kill()
        subprocess.run([*command, "kill-server"], capture_output=True)
