"""pytest-embedded-arduino-cli plugin for CH32 boards flashed by ch32rv.

pytest-embedded-arduino-cli already uploads (ch32rv, through the platform's upload recipe) and gives the test a `dut`
read through the platform's own monitor (ch32rv). This plugin adds what a CH32 bench test needs on top:

- `ch32rv`     the ch32rv the platform installed (runtime.tools.ch32rv.path), as a path.
- `oep_host`   an oep-client-python Host on the OEP probe behind the test's port, through ch32rv's broker.
- `ch32_uart`  the DUT's UART as the probe sees it, opened at a baud rate: a WCH-Link's UART bridge, or an OEP probe's
               oep.fixture.uart. Same expect / expect_exact / write shape as `dut` (pexpect underneath).

It knows ch32rv and OEP, not the board: which DUT USART is wired to the probe is the test's (the bench's) business.
The fixtures are the plugin's interface; every other name here is internal.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pexpect
import pexpect.spawnbase
import pytest

_LEASE_MS = 60000                  # oep-spec: probes accept 1000..60000 as asked
_KEEPALIVE_S = _LEASE_MS / 3000.0  # refresh a third of the way in, on the next use
_BROKER_WAIT_S = 10.0              # for the dut's monitor to start the broker
_EXPECT_TIMEOUT_S = 30.0           # pytest-embedded's Dut default
_SHARE = "oep.probe.share"  # host guide §7.1: a broker shares the lock its tools (monitor / flash / gdb) hold


# ------------------------------------------------------------------ the test's port and the probe behind it

def _dut_address(config: pytest.Config) -> str:
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


def _run_ch32rv(ch32rv: Path, *args: str, timeout: float = 30.0) -> dict:
    out = subprocess.run([str(ch32rv), *args], capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ch32rv {' '.join(args)} gave no JSON (exit {out.returncode}): {out.stderr.strip()}") from e


def _wch_link_uart(ch32rv: Path, address: str) -> str | None:
    """The UART bridge (CDC serial port) of the WCH-Link behind `address`, or None when it is not a WCH-Link: the
    WCH-Link rows of `probe list` (an OEP probe's CDC there is the OEP link, not a UART bridge), matched by the
    row's address (`wchlink://<serial>`, `wchlink://usb-<topology>`), its serial, or one of its serial ports."""
    probes = [p for p in _run_ch32rv(ch32rv, "probe", "list", "--json")["result"]["probes"] if p["kind"] == "wchlink"]
    want = None if "://" in address else os.path.realpath(address)
    for p in probes:
        if not p["ports"]:
            continue
        if address == p.get("address") or address.lower() == f"wchlink://{p['serial']}".lower():
            return p["ports"][0]
        for port in p["ports"]:
            if want is not None and os.path.realpath(port) == want:
                return port
    return None


def _oep_port(address: str) -> str | None:
    """The port of an `oep://<probe>[/<port>[/<target>]][?via=<route>]` address (host guide §5.3), or None: no port
    in it, or not an oep:// address. The query comes off first: a route (`tty:/dev/...`, `tcp:host:port`) has `/`."""
    if not address.lower().startswith("oep://"):
        return None
    place = address[len("oep://"):].partition("?")[0]
    parts = place.split("/")
    return parts[1] if len(parts) > 1 and parts[1] else None


# ------------------------------------------------------------------ one expect-able byte channel

class _Stream(pexpect.spawnbase.SpawnBase):
    """pexpect over a read callback that returns what arrived without waiting (b"" for nothing yet)."""

    def __init__(self, read, timeout: float):
        super().__init__(timeout=timeout)
        self._read_now = read

    def read_nonblocking(self, size: int = 1, timeout: float | None = -1) -> bytes:
        if timeout == -1:
            timeout = self.timeout
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            data = self._read_now()
            if data:
                self._log(data, "read")
                return data
            if end is not None and time.monotonic() >= end:
                raise pexpect.TIMEOUT("Timeout exceeded.")
            time.sleep(0.01)


class _Channel:
    """A byte stream shaped like pytest-embedded's Dut for what a bench test does with it: expect / expect_exact
    (pexpect's, with the Dut's keywords expect_all, not_matching, return_what_before_match; the default timeout
    30 s; pexpect.TIMEOUT when nothing matched) and write."""

    def __init__(self, read, write, name: str):
        self._write, self.name = write, name
        self._proc = _Stream(read, _EXPECT_TIMEOUT_S)

    def write(self, data: str | bytes) -> None:
        self._write(data.encode() if isinstance(data, str) else data)

    def expect(self, pattern, **kwargs):
        return self._expect(self._proc.expect, pattern, **kwargs)

    def expect_exact(self, pattern, **kwargs):
        return self._expect(self._proc.expect_exact, pattern, **kwargs)

    def _expect(self, func, pattern, *, expect_all: bool = False, not_matching=(),
                return_what_before_match: bool = False, **kwargs):
        """The Dut's expect wrapper (pytest_embedded.dut), on this channel's pexpect."""
        if return_what_before_match and expect_all:
            raise ValueError("`return_what_before_match` and `expect_all` cannot be `True` at the same time.")
        patterns = list(pattern) if isinstance(pattern, (list, tuple)) else [pattern]
        res = []
        while patterns:
            try:
                index = func(patterns, **kwargs)
            except (pexpect.EOF, pexpect.TIMEOUT) as e:
                tail = bytes((self._proc.before or b"")[-200:])
                raise e.__class__(f'{self.name}: not found "{pattern!s}"; last bytes: {tail!r}') from e
            proc = self._proc
            res.append(proc.before.rstrip() if proc.match in (pexpect.EOF, pexpect.TIMEOUT) else proc.match)
            nms = not_matching if isinstance(not_matching, (list, tuple)) else [not_matching]
            for nm in nms:
                rx = re.compile(nm.encode() if isinstance(nm, str) else
                                nm.pattern.encode() if isinstance(nm.pattern, str) else nm.pattern)
                if rx.search(proc.before):
                    raise ValueError(f"The pattern {rx} should not have been matched.")
            if not expect_all:
                break
            patterns.pop(index)
        if return_what_before_match:
            return self._proc.before
        return res[0] if len(res) == 1 else res


class _Ch32Uart:
    """The DUT's UART on the probe. `open(baud)` (again to change the rate) returns the Channel."""

    def __init__(self, request: pytest.FixtureRequest, ch32rv: Path):
        self._request, self._ch32rv = request, ch32rv
        self.address = _dut_address(request.config)
        self.channel: _Channel | None = None
        self._close = None

    def open(self, baud: int) -> _Channel:
        self.close()
        bridge = _wch_link_uart(self._ch32rv, self.address)
        if bridge is not None:
            import serial
            s = serial.Serial(bridge, baud, timeout=0, exclusive=True)
            self.channel = _Channel(lambda: s.read(4096), s.write, f"uart {bridge} @{baud}")
            self._close = s.close
        else:
            host = self._request.getfixturevalue("oep_host")
            self.channel = host._fixture_uart(baud, name=f"uart {self.address} @{baud}", port=_oep_port(self.address))
            self._close = None
        return self.channel

    def close(self) -> None:
        if self._close:
            self._close()
        self._close, self.channel = None, None


# ------------------------------------------------------------------ the OEP probe, through ch32rv's broker

class _OepHost:
    """The `oep_host` fixture: an oep-client-python Host in a session on the probe behind the test's port, through
    ch32rv's broker (the one the dut's monitor started). The open asks the broker to share the lock its own tools
    hold (host guide §7.1's named extension oep.probe.share), so the session runs beside the dut's monitor; an
    endpoint that does not know the extension gets a plain open. Its interface is `host` (the Host) and `touch()`,
    which keeps the session's lease alive and runs on every use through `ch32_uart` - a test that goes quiet for
    longer than the lease (60 s) loses its session."""

    def __init__(self, endpoint: str, owner: str):
        from oep_client import host as oh, link, message as m
        self._link = link.SerialLink.on_stream(link.TcpStream(*_split(endpoint)), "length", 3.0)
        self.host = oh.Host(self._link.send)
        self._link.attach_host(self.host)
        try:
            self.host.open(_LEASE_MS, owner=owner, extensions=[_SHARE])
        except oh.Unsupported as e:
            if e.tag != m.TAG_NAMED_EXTENSION | m.TAG_CRITICAL:
                raise
            self.host.open(_LEASE_MS, owner=owner)  # not ch32rv's broker: a session of its own
        self._last = time.monotonic()

    def touch(self) -> None:
        if time.monotonic() - self._last > _KEEPALIVE_S:
            self.host.keepalive()
        self._last = time.monotonic()

    def _fixture_uart(self, baud: int, name: str, port: str | None = None) -> _Channel:
        """The first oep.fixture.uart that takes `baud`, planned onto the port's rx / tx lines: the channels labelled
        `<port>.rx` / `<port>.tx` (host guide §5.3; a label may add the target pin, `<port>.rx@pa10`). `port` is the
        `<port>` of `oep://<probe>/<port>`; without it the probe must name one port. The plan is the session's."""
        from oep_client import core, fixture, host as oh, registry, settings
        RX, TX = (registry.FIXTURE_UART.enum["role"][r] for r in ("rx", "tx"))
        # Every channel label (fixed / default / user), from the core's settings.
        labels = settings.labels(self.host)
        ports = settings.ports_named(labels)
        if port is None and len(ports) > 1:
            raise RuntimeError(f"the probe names ports {', '.join(ports)}: give the test's port as "
                               f"oep://<probe>/<port> to say which one the DUT's UART is on")
        port_name = port if port is not None else (ports[0] if ports else None)
        rx, tx = (settings.line_from_labels(labels, line, port_name) for line in ("rx", "tx"))
        if rx is None or tx is None:
            where = f"{port_name}." if port_name else ""
            raise RuntimeError(f"no single {where}rx / {where}tx line in the probe's labels (rx {rx}, tx {tx}; "
                               f"ports: {', '.join(ports) or 'none'}): label them, oep settings set <probe> core "
                               f"channel.<GPIO>.label={where}rx channel.<GPIO>.label={where}tx --save")
        last = None
        for fn in core.find_all(self.host, "oep.fixture.uart"):
            io = fixture.FixtureUartIO(self.host, fn)
            try:
                core.plan_apply(self.host, [(fn, RX, rx), (fn, TX, tx)])
            except oh.Rejected as e:
                last = e
                continue
            try:
                io.configure(baud)
            except oh.Rejected as e:          # free the pins for the next instance
                last = e
                core.plan_release(self.host, [fn])
                continue

            def read(io=io):
                self.touch()
                return io.read(480)

            def write(data: bytes, io=io):
                self.touch()
                io.write(data)

            return _Channel(read, write, f"{name} (fn {fn}, rx {rx}, tx {tx})")
        raise RuntimeError(f"no oep.fixture.uart on this probe takes rx {rx} / tx {tx} at {baud} baud ({last})")

    def close(self) -> None:
        try:
            self.host.end()
        finally:
            self._link.close()


def _split(endpoint: str) -> tuple[str, int]:
    host, _, port = endpoint.rpartition(":")
    return host or "127.0.0.1", int(port)


# ------------------------------------------------------------------ the device lock

def _device_identity(port: str) -> str | None:
    """The device behind `port`, without opening it; lower case. An OEP probe: its unit_id, without the port, target
    and route (host guide §5.3). A WCH-Link: its USB serial. A serial port path: the USB serial of the device it
    belongs to, read from the OS's device list (sysfs; the port is not opened) - a WCH-Link's serial, or a USB OEP
    probe's, which is its unit_id. ch32rv's broker serves a WCH-Link as an OEP probe whose unit_id is that serial,
    so `/dev/ttyACM5`, `wchlink://<serial>` and `oep://<serial>?via=tcp:...` are one device. None when the address
    says nothing more (a USB-UART without a serial, `wchlink://usb-<topology>`): the upstream rule keys it."""
    from pytest_embedded_arduino_cli import MonitorTarget, is_monitor_url
    if is_monitor_url(port):
        port = MonitorTarget.from_url(port).address
    low = port.lower()
    if low.startswith("oep://"):
        unit = low[len("oep://"):].partition("?")[0].split("/")[0]
        return unit or None
    if low.startswith("wchlink://"):
        serial = low[len("wchlink://"):]
        return serial if serial and not serial.startswith("usb-") else None
    if "://" in port or not os.path.exists(port):
        return None
    from serial.tools import list_ports
    want = os.path.realpath(port)
    for info in list_ports.comports():
        if os.path.realpath(info.device) == want:
            return info.serial_number.lower() if info.serial_number else None
    return None


@pytest.hookimpl(optionalhook=True)
def pytest_arduino_cli_device_lock_key(config: pytest.Config, port: str) -> str | None:
    """pytest-embedded-arduino-cli's device lock key: one key per probe, whichever of its ports or routes names it."""
    identity = _device_identity(port)
    return None if identity is None else f"ch32rv-probe:{identity}"


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
    address = _dut_address(request.config)
    # The broker is the one the dut's monitor starts, and `arduino-cli monitor` takes about a second to open
    # its session; a test that asks for oep_host first thing would otherwise find no broker yet.
    deadline = time.monotonic() + _BROKER_WAIT_S
    while True:
        endpoint = _run_ch32rv(ch32rv, "broker", "endpoint", "--probe", address, "--json")["result"]["endpoint"]
        if endpoint or time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    if not endpoint:
        raise RuntimeError(f"no ch32rv broker for {address} after {_BROKER_WAIT_S:g} s: is it an OEP probe, and "
                           f"did the dut's monitor open?")
    h = _OepHost(endpoint, owner=f"pytest {request.node.nodeid}"[:32])
    try:
        yield h
    finally:
        h.close()


@pytest.fixture
def ch32_uart(request: pytest.FixtureRequest, ch32rv: Path, dut):
    """The DUT's UART as the probe sees it; `ch32_uart.open(baud)` returns an expect-able Channel. Which DUT USART
    and route are wired to the probe is the test's to tell the sketch."""
    u = _Ch32Uart(request, ch32rv)
    try:
        yield u
    finally:
        u.close()
