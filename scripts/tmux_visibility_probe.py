#!/usr/bin/env python3
"""Print a line each time tmux reports a change that can affect this window's visibility.

Run inside tmux. Connects a control-mode client to the tmux server of this pane, attached
to a new session of its own, so that the user's sessions stay unattached. The session is
destroyed on exit.

Prints each notification. After each one, queries the visibility of this pane's window with
display-message, and prints the result.
"""

import os
import subprocess
import sys
from datetime import datetime

VISIBILITY_FORMAT = "viewers=#{window_active_clients_list}"


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S.%f}"[:-3], message, flush=True)


def visibility(value: str) -> str:
    viewers = [c for c in value.removeprefix("viewers=").split(",") if c]
    return f"visible={bool(viewers)} viewers={viewers}"


def main() -> None:
    tmux_env = os.environ.get("TMUX")
    pane = os.environ.get("TMUX_PANE")
    if not tmux_env or not pane:
        sys.exit("Run this inside tmux")
    socket = tmux_env.split(",")[0]
    session = f"_ggb-probe-{os.getpid()}"

    env = dict(os.environ)
    # tmux refuses to start a client inside tmux unless $TMUX is unset
    del env["TMUX"]
    proc = subprocess.Popen(
        ["tmux", "-S", socket, "-C", "new-session", "-s", session, "sleep 2147483647"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    assert proc.stdin and proc.stdout

    def send(command: str) -> None:
        log(f"> {command}")
        assert proc.stdin
        proc.stdin.write(command + "\n")
        proc.stdin.flush()

    send(f"set-option -t {session} destroy-unattached on")
    query = f"display-message -p -t {pane} '{VISIBILITY_FORMAT}'"
    send(query)
    log(f"Watching pane {pane} from session {session}. Press Ctrl-C to stop.")

    in_block = False
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("%begin"):
                in_block = True
            elif line.startswith(("%end", "%error")):
                if line.startswith("%error"):
                    log(f"  {line}")
                in_block = False
            elif in_block:
                if line.startswith("viewers="):
                    log(f"    -> {visibility(line)}")
                else:
                    log(f"  {line}")
            elif line.startswith("%exit"):
                log(line)
                break
            elif line.startswith(("%output", "%extended-output")):
                pass
            elif line.startswith("%"):
                log(line)
                proc.stdin.write(query + "\n")
                proc.stdin.flush()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.stdin.write(f"kill-session -t {session}\n")
            proc.stdin.close()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
