"""pytest-embedded-arduino-cli plugin for CH32 boards flashed by ch32rv.

pytest-embedded-arduino-cli already uploads (ch32rv, through the platform's upload recipe) and gives the test a `dut`
read through the platform's own monitor (ch32rv). This plugin adds what a CH32 bench test needs on top:

- `ch32rv`     the ch32rv the platform installed (runtime.tools.ch32rv.path), as a path.
- `oep_host`   an oep-client-python Host on the OEP probe behind the test's port, through ch32rv's broker.
- `ch32_uart`  the DUT's UART as the probe sees it, opened at a baud rate: a WCH-Link's UART bridge, or an OEP probe's
               oep.fixture.uart. Same expect / expect_exact / write shape as `dut`.

It knows ch32rv and OEP, not the board: which DUT USART is wired to the probe is the test's (the bench's) business.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

LEASE_MS = 60000                 # oep-spec: probes accept 1000..60000 as asked
KEEPALIVE_S = LEASE_MS / 3000.0  # refresh a third of the way in, on the next use
BROKER_WAIT_S = 10.0             # for the dut's monitor to start the broker


# ------------------------------------------------------------------ the test's port and the probe behind it

def dut_address(config: pytest.Config) -> str:
    """The IDE-style port the test runs against: --port as resolved by pytest-embedded-arduino-cli, with the wrapper
    it adds for a platform monitor taken off through its own MonitorTarget (public API since 1.8.0; the URL's
    spelling is not a contract)."""
    from pytest_embedded_arduino_cli import MonitorTarget, is_monitor_url
    port = config.getoption("port", None) or ""
    if is_monitor_url(port):
        port = MonitorTarget.from_url(port).address
    if not port:
        raise pytest.UsageError("pytest-embedded-arduino-cli-ch32rv: no port (--port, or TEST_SERIAL_PORT_<PROFILE>)")
    return port


def run_ch32rv(ch32rv: Path, *args: str, timeout: float = 30.0) -> dict:
    out = subprocess.run([str(ch32rv), *args], capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ch32rv {' '.join(args)} gave no JSON (exit {out.returncode}): {out.stderr.strip()}") from e


def wch_link_uart(ch32rv: Path, address: str) -> str | None:
    """The UART bridge (CDC serial port) of the WCH-Link behind `address`, or None when it is not a WCH-Link:
    `wchlink://<serial>` names it by serial; a serial port path is a WCH-Link's own CDC when `probe list` says so."""
    probes = run_ch32rv(ch32rv, "probe", "list", "--json").get("result", {}).get("probes", [])
    if address.startswith("wchlink://"):
        serial = address[len("wchlink://"):]
        for p in probes:
            if p.get("serial") == serial and p.get("ports"):
                return p["ports"][0]
        return None
    want = os.path.realpath(address)
    for p in probes:
        for port in p.get("ports", []):
            if os.path.realpath(port) == want:
                return port
    return None


# ------------------------------------------------------------------ one expect-able byte channel

class Channel:
    """A byte stream with the part of pytest-embedded's Dut interface a bench test uses: expect (regex),
    expect_exact, write. `read` returns what arrived without waiting."""

    def __init__(self, read, write, name: str):
        self._read, self._write, self.name = read, write, name
        self.buffer = b""
        self.log = bytearray()

    def _fill(self) -> None:
        data = self._read()
        if data:
            self.buffer += data
            self.log += data

    def write(self, data: str | bytes) -> None:
        self._write(data.encode() if isinstance(data, str) else data)

    def expect(self, pattern: str | bytes, timeout: float = 5.0) -> re.Match:
        rx = re.compile(pattern.encode() if isinstance(pattern, str) else pattern)
        end = time.monotonic() + timeout
        while True:
            m = rx.search(self.buffer)
            if m:
                self.buffer = self.buffer[m.end():]
                return m
            if time.monotonic() > end:
                raise TimeoutError(f"{self.name}: {pattern!r} not seen in {timeout} s; last bytes: {bytes(self.buffer[-200:])!r}")
            self._fill()
            time.sleep(0.01)

    def expect_exact(self, text: str | bytes, timeout: float = 5.0) -> bytes:
        return self.expect(re.escape(text.encode() if isinstance(text, str) else text), timeout).group(0)

    def read(self) -> bytes:
        self._fill()
        out, self.buffer = self.buffer, b""
        return out


class Ch32Uart:
    """The DUT's UART on the probe. `open(baud)` (again to change the rate) returns the Channel."""

    def __init__(self, request: pytest.FixtureRequest, ch32rv: Path):
        self._request, self._ch32rv = request, ch32rv
        self.address = dut_address(request.config)
        self.channel: Channel | None = None
        self._close = None

    def open(self, baud: int) -> Channel:
        self.close()
        bridge = wch_link_uart(self._ch32rv, self.address)
        if bridge is not None:
            import serial
            s = serial.Serial(bridge, baud, timeout=0, exclusive=True)
            self.channel = Channel(lambda: s.read(4096), s.write, f"uart {bridge} @{baud}")
            self._close = s.close
        else:
            host = self._request.getfixturevalue("oep_host")
            self.channel = host.fixture_uart(baud, name=f"uart {self.address} @{baud}")
            self._close = None
        return self.channel

    def close(self) -> None:
        if self._close:
            self._close()
        self._close, self.channel = None, None


# ------------------------------------------------------------------ the OEP probe, through ch32rv's broker

class OepHost:
    """An oep-client-python Host in a session on the probe behind the test's port, through ch32rv's broker (the
    one the dut's monitor started). `host` is the Host; `touch()` keeps the session's lease alive and runs on every
    use through this object - a test that goes quiet for longer than the lease (60 s) loses its session."""

    def __init__(self, endpoint: str, owner: str):
        from oep_client import host as oh, link
        self.link = link.SerialLink.on_stream(link.TcpStream(*_split(endpoint)), "length", 3.0)
        self.host = oh.Host(self.link.send)
        self.link.attach_host(self.host)
        self.host.open(LEASE_MS, owner=owner)
        self._last = time.monotonic()

    def touch(self) -> None:
        if time.monotonic() - self._last > KEEPALIVE_S:
            self.host.keepalive()
        self._last = time.monotonic()

    def fixture_uart(self, baud: int, name: str) -> Channel:
        """The first oep.fixture.uart that takes `baud`: one whose pins the probe's saved plan assigned
        (`oep config plan <probe> oep.fixture.uart#<n> rx=.. tx=.. --save`); the others refuse as unavailable."""
        from oep_client import core, fixture, host as oh
        last = None
        for fn in core.find_all(self.host, "oep.fixture.uart"):
            io = fixture.FixtureUartIO(self.host, fn)
            try:
                io.configure(baud)
            except oh.Rejected as e:
                last = e
                continue

            def read(io=io):
                self.touch()
                return io.read(480)

            def write(data: bytes, io=io):
                self.touch()
                io.write(data)

            return Channel(read, write, f"{name} (fn {fn})")
        raise RuntimeError(f"no oep.fixture.uart on this probe has pins for the DUT's UART ({last}); give one a "
                           f"plan: oep config plan <probe> oep.fixture.uart#<n> rx=<ch> tx=<ch> --save")

    def close(self) -> None:
        try:
            self.host.end()
        finally:
            self.link.close()


def _split(endpoint: str) -> tuple[str, int]:
    host, _, port = endpoint.rpartition(":")
    return host or "127.0.0.1", int(port)


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module")
def ch32rv(arduino_cli_build_properties) -> Path:
    """The ch32rv the platform installed for this sketch's board (runtime.tools.ch32rv.path)."""
    base = arduino_cli_build_properties.get("runtime.tools.ch32rv.path")
    if not base:
        raise pytest.UsageError("this board's platform declares no ch32rv tool (runtime.tools.ch32rv.path)")
    exe = Path(base) / ("ch32rv.exe" if sys.platform == "win32" else "ch32rv")
    if not exe.exists():
        raise pytest.UsageError(f"ch32rv not found at {exe}")
    return exe


@pytest.fixture
def oep_host(request: pytest.FixtureRequest, ch32rv: Path, dut):
    """A session on the OEP probe behind the test's port, through the broker the dut's monitor runs. Fails (does
    not skip) when the port is not an OEP probe: a test that asks for it needs one."""
    address = dut_address(request.config)
    # The broker is the one the dut's monitor starts, and `arduino-cli monitor` takes about a second to open
    # its session; a test that asks for oep_host first thing would otherwise find no broker yet.
    deadline = time.monotonic() + BROKER_WAIT_S
    while True:
        info = run_ch32rv(ch32rv, "broker", "endpoint", "--probe", f"port:{address}", "--json")
        endpoint = info.get("endpoint") or info.get("result", {}).get("endpoint")
        if endpoint or time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    if not endpoint:
        raise RuntimeError(f"no ch32rv broker for {address} after {BROKER_WAIT_S:g} s: is it an OEP probe, and "
                           f"did the dut's monitor open?")
    h = OepHost(endpoint, owner=f"pytest {request.node.nodeid}"[:32])
    try:
        yield h
    finally:
        h.close()


@pytest.fixture
def ch32_uart(request: pytest.FixtureRequest, ch32rv: Path, dut):
    """The DUT's UART as the probe sees it; `ch32_uart.open(baud)` returns an expect-able Channel. Which DUT USART
    and route are wired to the probe is the test's to tell the sketch."""
    u = Ch32Uart(request, ch32rv)
    try:
        yield u
    finally:
        u.close()
