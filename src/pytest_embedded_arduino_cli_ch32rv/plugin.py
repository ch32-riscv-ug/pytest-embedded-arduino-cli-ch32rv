"""pytest-embedded-arduino-cli plugin for CH32 boards flashed by ch32rv.

pytest-embedded-arduino-cli already uploads (ch32rv, through the platform's upload recipe) and gives the test a `dut`
read through the platform's own monitor (ch32rv). This plugin adds what a CH32 bench test needs on top:

- `ch32rv`     the ch32rv the platform installed (runtime.tools.ch32rv.path), as a path.
- `ch32_uart`  the DUT's UART through the WCH-Link behind the test's port (its UART bridge), opened at a baud rate.
               Same expect / expect_exact / write shape as `dut` (pexpect underneath).

and the device lock's name for a WCH-Link. OEP probes are oep-client-python's (its pytest plugin: `oep_host`,
`oep_uart`, the lock of `oep://` and of a USB OEP probe's serial port). It knows ch32rv and the WCH-Link, not the
board: which DUT USART is wired to the Link is the test's (the bench's) business. The fixtures and the hook are the
plugin's interface; every other name here is internal.
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

_EXPECT_TIMEOUT_S = 30.0  # pytest-embedded's Dut default
_OTHER_BAUD = 9600         # the rate ch32_uart passes through before the asked one
_WCH_LINK_USB = {(0x1A86, 0x8010), (0x1A86, 0x8011), (0x1A86, 0x8012)}  # ch32rv's wchlink: RISC-V, RISC-V 2, DAP


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
    """The DUT's UART through the WCH-Link. `open(baud)` (again to change the rate) returns the Channel."""

    def __init__(self, request: pytest.FixtureRequest, ch32rv: Path):
        self._request, self._ch32rv = request, ch32rv
        self.address = _dut_address(request.config)
        self.channel: _Channel | None = None
        self._close = None

    def open(self, baud: int) -> _Channel:
        self.close()
        if self.address.lower().startswith("oep://"):
            raise RuntimeError(f"{self.address} is an OEP probe: its UART is oep-client-python's `oep_uart` fixture")
        bridge = _wch_link_uart(self._ch32rv, self.address)
        if bridge is None:
            raise RuntimeError(f"no WCH-Link behind {self.address} in `ch32rv probe list` (an OEP probe's UART is "
                               f"oep-client-python's `oep_uart` fixture)")
        import serial
        # Open at another rate, then switch: the line coding changes on the Link (SET_LINE_CODING), which rebuilds
        # its UART bridge. A CH549 WCH-Link's bridge can be left running late (every byte from the DUT out a fixed
        # count behind, the last run's bytes first); opening straight at the same rate as before keeps that.
        s = serial.Serial(bridge, _OTHER_BAUD if baud != _OTHER_BAUD else 115200, timeout=0, exclusive=True)
        s.baudrate = baud
        s.reset_input_buffer()
        self.channel = _Channel(lambda: s.read(4096), s.write, f"uart {bridge} @{baud}")
        self._close = s.close
        return self.channel

    def close(self) -> None:
        if self._close:
            self._close()
        self._close, self.channel = None, None


# ------------------------------------------------------------------ the device lock

def _unit_id(serial: str) -> str:
    """A WCH-Link's unit_id the way ch32rv's broker gives it (wch_unit_id): lower case, a character other than ASCII
    letters and digits as `-`, at most 32 - the `<id>` of the OEP family's lock name `probe:<id>`."""
    return "".join(c if c.isascii() and c.isalnum() else "-" for c in serial.lower())[:32]


def _wch_link_serial(port: str) -> str | None:
    """The serial of the WCH-Link behind `port` without opening anything: `wchlink://<serial>`, or a serial port of a
    WCH-Link (USB 1a86:8010 / 8011 / 8012), read from the OS's device list. None otherwise - `wchlink://usb-<topology>`
    (no serial in it), an `oep://` address or a USB OEP probe's port (oep-client-python's), any other port."""
    from pytest_embedded_arduino_cli import MonitorTarget, is_monitor_url
    if is_monitor_url(port):
        port = MonitorTarget.from_url(port).address
    if port.lower().startswith("wchlink://"):
        serial = port[len("wchlink://"):]
        return serial if serial and not serial.lower().startswith("usb-") else None
    if "://" in port or not os.path.exists(port):
        return None
    from serial.tools import list_ports
    want = os.path.realpath(port)
    for info in list_ports.comports():
        if os.path.realpath(info.device) == want:
            return info.serial_number if (info.vid, info.pid) in _WCH_LINK_USB and info.serial_number else None
    return None


@pytest.hookimpl(optionalhook=True)
def pytest_arduino_cli_device_lock_key(config: pytest.Config, port: str) -> str | None:
    """pytest-embedded-arduino-cli's device lock name for a WCH-Link: `probe:<unit_id>`, the OEP family's name, as
    ch32rv's broker serves the Link as an OEP probe with that unit_id - `wchlink://<serial>`, the Link's serial port
    and `oep://<unit_id>?via=...` (oep-client-python's) take one lock. None for anything else."""
    serial = _wch_link_serial(port)
    return None if serial is None else f"probe:{_unit_id(serial)}"


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
def ch32_uart(request: pytest.FixtureRequest, ch32rv: Path, dut):
    """The DUT's UART through the WCH-Link behind the test's port; `ch32_uart.open(baud)` returns an expect-able
    Channel. Which DUT USART and route are wired to the Link is the test's to tell the sketch."""
    u = _Ch32Uart(request, ch32rv)
    try:
        yield u
    finally:
        u.close()
