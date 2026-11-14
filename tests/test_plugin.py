"""Board-free checks of the plugin: the parts that do not need a probe."""
import types

import pytest

from pytest_embedded_arduino_cli_ch32rv import plugin

pytest_plugins = ["pytester"]


def config_with_port(port):
    return types.SimpleNamespace(getoption=lambda name, default=None: port if name == "port" else default)


def wrapped(address: str, protocol: str, profile: str) -> str:
    """A platform-monitor port the way pytest-embedded-arduino-cli hands it over. Built through its MonitorTarget:
    the URL's spelling is the upstream plugin's business (its public API since 1.8.0), not a string this plugin knows."""
    from pathlib import Path

    from pytest_embedded_arduino_cli import MonitorTarget
    return MonitorTarget(address, Path("/tmp/x"), profile=profile, protocol=protocol).to_url()


@pytest.mark.parametrize("port, address", [
    ("/dev/ttyACM3", "/dev/ttyACM3"),
    ("wchlink://FBC18F0680B0", "wchlink://FBC18F0680B0"),
    (wrapped("/dev/ttyACM3", "serial", "ch32v203"), "/dev/ttyACM3"),
    (wrapped("oep://30eda0e31108-hs/x035", "oep", "ch32x035"), "oep://30eda0e31108-hs/x035"),
])
def test_dut_address_takes_the_monitor_wrapper_off(port, address):
    assert plugin._dut_address(config_with_port(port)) == address


def test_dut_address_without_a_port_is_a_usage_error():
    with pytest.raises(pytest.UsageError):
        plugin._dut_address(config_with_port(None))


def channel(chunks):
    sent = []
    it = iter(chunks)
    return plugin._Channel(lambda: next(it, b""), sent.append, "test"), sent


def test_channel_expect_and_expect_exact_consume_up_to_the_match():
    ch, sent = channel([b"hello from ", b"ch32\r\nint=42\r\n", b"hex=BEEF\r\n"])
    assert ch.expect_exact("hello from ch32") == b"hello from ch32"
    assert ch.expect(r"int=(\d+)").group(1) == b"42"
    assert ch.expect_exact("hex=BEEF")
    ch.write("RUN\n")
    assert sent == [b"RUN\n"]


def test_channel_takes_the_duts_keywords():
    ch, _ = channel([b"a=1 b=2 c=3\r\n"])
    assert ch.expect([r"x=(\d)", r"b=(\d)"]).group(1) == b"2"
    assert ch.expect_exact("3", return_what_before_match=True) == b" c="
    ch, _ = channel([b"one two three"])
    assert [m.group(0) for m in ch.expect([r"three", r"one"], expect_all=True)] == [b"one", b"three"]
    ch, _ = channel([b"error ok"])
    with pytest.raises(ValueError):
        ch.expect("ok", not_matching=["error"])


def test_channel_expect_times_out_like_the_dut_with_the_tail_in_the_message():
    import pexpect
    ch, _ = channel([b"garbage"])
    with pytest.raises(pexpect.TIMEOUT, match="garbage"):
        ch.expect_exact("never", timeout=0.1)


# ch32rv `probe list --json` (contract 5): every row has `kind`; the OEP probes ch32rv enumerates over USB are there
# too, their CDC (the OEP link itself, not a UART bridge) in `ports`.
PROBES = {"result": {"probes": [
    {"kind": "wchlink", "serial": "FBC18F0680B0", "usb": "1a86:8010", "ports": ["/dev/ttyACM3"],
     "address": "wchlink://FBC18F0680B0"},
    {"kind": "wchlink", "serial": "434A124C5596", "usb": "1a86:8010", "ports": ["/dev/ttyACM1"],
     "address": "wchlink://usb-3-1.2"},
    {"kind": "oep", "serial": "9489dd2ae0953650", "usb": "1209:0001", "ports": ["/dev/ttyACM5"],
     "address": "oep://9489dd2ae0953650"},
]}}


@pytest.mark.parametrize("address, bridge", [
    ("wchlink://FBC18F0680B0", "/dev/ttyACM3"),
    ("/dev/ttyACM1", "/dev/ttyACM1"),
    ("wchlink://434A124C5596", "/dev/ttyACM1"),
    ("wchlink://usb-3-1.2", "/dev/ttyACM1"),
    ("oep://30eda0e31108-hs/x035", None),
    ("oep://9489dd2ae0953650/l103", None),
    ("/dev/ttyACM5", None),
    ("/dev/ttyUSB0", None),
])
def test_wch_link_uart_maps_the_port_to_the_links_bridge(monkeypatch, address, bridge):
    monkeypatch.setattr(plugin, "_run_ch32rv", lambda ch32rv, *args, **kw: PROBES)
    assert plugin._wch_link_uart("ch32rv", address) == bridge


@pytest.mark.parametrize("port, key", [
    ("wchlink://38EF8F06BDC2", "probe:38ef8f06bdc2"),
    (wrapped("wchlink://38EF8F06BDC2", "wchlink", "ch32v203"), "probe:38ef8f06bdc2"),
    ("wchlink://usb-3-1.2", None),
    ("oep://30eda0e31108-hs/x035", None),
    ("oep://38ef8f06bdc2?via=tcp:127.0.0.1:4242", None),
    ("socket://localhost:5555", None),
])
def test_the_device_lock_name_is_the_wch_links(port, key):
    assert plugin.pytest_arduino_cli_device_lock_key(None, port) == key


def test_the_device_lock_name_of_a_wch_links_serial_port_is_its_unit_id(monkeypatch, tmp_path):
    """A WCH-Link's tty takes the Link's lock (its USB serial from the OS's list, the port not opened); any other
    USB serial port is not this plugin's (a USB OEP probe's is oep-client-python's)."""
    from serial.tools import list_ports
    link, oep, bridge, alias = (tmp_path / n for n in ("ttyACM5", "ttyACM6", "ttyUSB0", "by-id-link"))
    link.touch(), oep.touch(), bridge.touch(), alias.symlink_to(link)
    ports = [types.SimpleNamespace(device=str(link), vid=0x1A86, pid=0x8010, serial_number="38EF8F06BDC2"),
             types.SimpleNamespace(device=str(oep), vid=0x1209, pid=0x4F45, serial_number="30eda0e31108"),
             types.SimpleNamespace(device=str(bridge), vid=0x1A86, pid=0x7523, serial_number=None)]
    monkeypatch.setattr(list_ports, "comports", lambda: ports)
    key = plugin.pytest_arduino_cli_device_lock_key
    assert key(None, str(link)) == key(None, str(alias)) == key(None, "wchlink://38EF8F06BDC2") \
        == "probe:38ef8f06bdc2"
    assert key(None, str(oep)) is None
    assert key(None, str(bridge)) is None
    assert key(None, str(tmp_path / "gone")) is None


def test_the_unit_id_is_ch32rvs():
    """ch32rv's wch_unit_id: lower case, other than ASCII letters and digits as `-`, at most 32."""
    assert plugin._unit_id("38EF8F06BDC2") == "38ef8f06bdc2"
    assert plugin._unit_id("AB_cd.12") == "ab-cd-12"
    assert plugin._unit_id("X" * 40) == "x" * 32


def test_ch32_uart_on_an_oep_port_points_to_oep_uart(monkeypatch):
    monkeypatch.setattr(plugin, "_run_ch32rv", lambda ch32rv, *args, **kw: PROBES)
    request = types.SimpleNamespace(config=config_with_port("oep://30eda0ea068b/v003"))
    with pytest.raises(RuntimeError, match="oep_uart"):
        plugin._Ch32Uart(request, "ch32rv").open(115200)
    request = types.SimpleNamespace(config=config_with_port("/dev/ttyUSB0"))
    with pytest.raises(RuntimeError, match="no WCH-Link"):
        plugin._Ch32Uart(request, "ch32rv").open(115200)


def test_the_fixtures_are_registered(pytester):
    result = pytester.runpytest("--fixtures")
    out = result.stdout.str()
    for name in ("ch32rv", "ch32_uart"):
        assert name in out
    assert "oep_host" not in out or "oep_client" in out  # oep_host is oep-client-python's, if that is installed


@pytest.mark.parametrize("baud, rates", [(115200, [9600, 115200]), (9600, [115200, 9600])])
def test_ch32_uart_passes_another_rate_first(monkeypatch, baud, rates):
    """The Link's bridge is rebuilt by a change of line coding: open at another rate, then the asked one, and drop
    what came before."""
    import serial
    seen = []

    class FakeSerial:
        def __init__(self, port, rate, **kw):
            seen.append(rate)

        @property
        def baudrate(self):
            return seen[-1]

        @baudrate.setter
        def baudrate(self, rate):
            seen.append(rate)

        def reset_input_buffer(self):
            seen.append("flush")

        def read(self, n):
            return b""

        write = close = lambda self, *a: None

    monkeypatch.setattr(plugin, "_run_ch32rv", lambda ch32rv, *args, **kw: PROBES)
    monkeypatch.setattr(serial, "Serial", FakeSerial)
    request = types.SimpleNamespace(config=config_with_port("wchlink://FBC18F0680B0"))
    plugin._Ch32Uart(request, "ch32rv").open(baud)
    assert seen == [*rates, "flush"]
