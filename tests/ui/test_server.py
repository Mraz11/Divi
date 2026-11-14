# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start the real server (not a simulation) and use it the way a browser would.

The server is started through a small wrapper process on purpose: on Windows a virtual
environment's python.exe is a launcher that runs the real interpreter as a child process, so
the program that listens is never the process we started. Doing the same everywhere makes the
tests check (and clean up) the whole process tree, as a real launch needs.
"""

import contextlib
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import psutil
import pytest

from avispria.app.ui.app import HOST, find_free_port

START = "from avispria.app.cli import app; app()"
WRAPPER = (
    "import subprocess, sys; "
    "sys.exit(subprocess.call([sys.executable, '-c', sys.argv[1], 'ui', "
    "'--port', sys.argv[2], '--no-browser']))"
)


def process_tree(pid: int) -> list[psutil.Process]:
    try:
        parent = psutil.Process(pid)
        return [parent, *parent.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def stop_tree(pid: int) -> None:
    tree = process_tree(pid)
    for p in tree:
        with contextlib.suppress(psutil.NoSuchProcess):
            p.terminate()
    _, alive = psutil.wait_procs(tree, timeout=15)
    for p in alive:
        with contextlib.suppress(psutil.NoSuchProcess):
            p.kill()


def listening_addresses(pid: int, port: int) -> set[str]:
    """Addresses the process (or any of its children) listens on for ``port``."""
    found: set[str] = set()
    for p in process_tree(pid):
        try:
            connections = p.net_connections(kind="inet")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        found |= {
            c.laddr.ip
            for c in connections
            if c.status == psutil.CONN_LISTEN and c.laddr.port == port
        }
    return found


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[int, subprocess.Popen[bytes]]]:
    port = find_free_port(18080)
    # NiceGUI switches into its own test mode when it sees pytest's variable: a real user's
    # environment never has it, so the program under test must not inherit it
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "NICEGUI_"))}
    proc = subprocess.Popen(
        [sys.executable, "-c", WRAPPER, START, str(port)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"the server stopped at start-up (exit code {proc.returncode})")
            try:
                if httpx.get(f"http://{HOST}:{port}/", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            pytest.fail("the server did not start in time")
        yield port, proc
    finally:
        stop_tree(proc.pid)
        proc.wait(15)
    # nothing may be left running: the port is free again
    for _ in range(50):
        if find_free_port(port, tries=1) == port:
            break
        time.sleep(0.1)
    else:
        pytest.fail(f"a server process is still running on port {port} after the test")


def test_the_real_server_serves_every_screen(server: tuple[int, subprocess.Popen[bytes]]) -> None:
    port, _ = server
    for path in ("/", "/check", "/plan", "/process"):
        reply = httpx.get(f"http://{HOST}:{port}{path}", timeout=10)
        assert reply.status_code == 200 and "Dīvi" in reply.text, path
    assert httpx.get(f"http://{HOST}:{port}/no-such-screen", timeout=10).status_code == 404


def test_the_real_server_serves_the_logo_and_the_colours(
    server: tuple[int, subprocess.Popen[bytes]],
) -> None:
    port, _ = server
    base = f"http://{HOST}:{port}"
    for name in ("logo.png", "logo-dark.png", "favicon.png"):
        reply = httpx.get(f"{base}/assets/{name}", timeout=10)
        assert reply.status_code == 200 and reply.headers["content-type"] == "image/png", name
        assert reply.content.startswith(b"\x89PNG"), name
    page = httpx.get(f"{base}/", timeout=10).text
    assert (
        "/assets/logo.png" in page and "/assets/logo-dark.png" in page
    )  # the header logo, both modes
    assert "data-theme" in page  # the script that picks light or dark before anything is drawn
    assert "--primary: #669762" in page  # the logo's vegetation green, both modes
    assert "--bg: #EDF1EE" in page and "--bg: #0E1714" in page  # mist, telemetry console


def test_the_real_server_listens_on_this_computer_only(
    server: tuple[int, subprocess.Popen[bytes]],
) -> None:
    port, proc = server
    tree = [p.pid for p in process_tree(proc.pid)]
    assert len(tree) >= 2  # the wrapper and the server: the layout a Windows launch has
    # what matters: from this computer's own network address the server cannot be reached
    for ip in network_addresses():
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://{ip}:{port}/", timeout=3)
    # and, where the system lists the server's socket, it is on 127.0.0.1 only. Some Windows
    # PCs do not list it at all (seen on the founder's PC: Get-NetTCPConnection is empty for the
    # port while the server answers on it): there the check above has to do
    addresses = listening_addresses(proc.pid, port)
    if addresses:
        assert addresses == {HOST}  # never 0.0.0.0


def network_addresses() -> list[str]:
    """This computer's IPv4 addresses other than loopback."""
    return sorted(
        {
            a.address
            for addresses in psutil.net_if_addrs().values()
            for a in addresses
            if a.family == socket.AF_INET and not a.address.startswith("127.")
        }
    )


def test_the_real_server_refuses_other_sites_and_hosts(
    server: tuple[int, subprocess.Popen[bytes]],
) -> None:
    port, _ = server
    base = f"http://{HOST}:{port}"
    assert httpx.get(f"{base}/", headers={"Host": f"localhost:{port}"}, timeout=10).is_success
    # DNS rebinding: a site whose own name now points at 127.0.0.1
    rebound = httpx.get(f"{base}/", headers={"Host": f"evil.example:{port}"}, timeout=10)
    assert rebound.status_code == 400
    # the live connection: Dīvi's own page may open it, another site may not
    poll = f"{base}/_nicegui_ws/socket.io/?EIO=4&transport=polling"
    own = httpx.get(poll, headers={"Origin": f"http://127.0.0.1:{port}"}, timeout=10)
    other = httpx.get(poll, headers={"Origin": "http://evil.example"}, timeout=10)
    assert own.status_code == 200 and other.status_code in {400, 403}
