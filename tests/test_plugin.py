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


@pytest.mark.parametrize("address, port", [
    ("oep://30eda0e31108-hs/x035", "x035"),
    ("oep://30eda0e31108-hs/x035/ch32x035-0123456789abcdef", "x035"),
    ("oep://30eda0e31108-hs", None),
    ("oep://30eda0e31108-hs?via=tty:/dev/serial/by-id/usb-x-if00", None),
    ("oep://30eda0e31108-hs/x035?via=tty:/dev/ttyACM0", "x035"),
    ("oep://38ef8f06bdc2/v003?via=tcp:127.0.0.1:4242", "v003"),
    ("/dev/ttyACM3", None),
])
def test_oep_port_is_the_port_of_an_oep_address(address, port):
    assert plugin._oep_port(address) == port


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
    ("oep://30EDA0E31108-hs/x035", "ch32rv-probe:30eda0e31108-hs"),
    ("oep://30eda0e31108-hs/l103/ch32l103-0123456789abcdef?via=usb", "ch32rv-probe:30eda0e31108-hs"),
    ("oep://30eda0e31108-hs?via=tty:/dev/ttyACM0", "ch32rv-probe:30eda0e31108-hs"),
    ("wchlink://38EF8F06BDC2", "ch32rv-probe:38ef8f06bdc2"),
    ("oep://38ef8f06bdc2?via=tcp:127.0.0.1:4242", "ch32rv-probe:38ef8f06bdc2"),
    (wrapped("oep://30eda0e31108-hs/x035", "oep", "ch32x035"), "ch32rv-probe:30eda0e31108-hs"),
    ("wchlink://usb-3-1.2", None),
    ("socket://localhost:5555", None),
])
def test_the_device_lock_key_is_the_probe(port, key):
    assert plugin.pytest_arduino_cli_device_lock_key(None, port) == key


def test_the_device_lock_key_of_a_serial_port_is_its_usb_serial(monkeypatch, tmp_path):
    """A tty names the same device as its probe's address: the USB serial from the OS's list, the port not opened."""
    from serial.tools import list_ports
    link, bridge, alias = tmp_path / "ttyACM5", tmp_path / "ttyUSB0", tmp_path / "by-id-link"
    link.touch(), bridge.touch(), alias.symlink_to(link)
    ports = [types.SimpleNamespace(device=str(link), serial_number="38EF8F06BDC2"),
             types.SimpleNamespace(device=str(bridge), serial_number=None)]
    monkeypatch.setattr(list_ports, "comports", lambda: ports)
    key = plugin.pytest_arduino_cli_device_lock_key
    assert key(None, str(link)) == key(None, str(alias)) == key(None, "wchlink://38EF8F06BDC2") \
        == key(None, "oep://38ef8f06bdc2?via=tcp:127.0.0.1:4242") == "ch32rv-probe:38ef8f06bdc2"
    assert key(None, str(bridge)) is None
    assert key(None, str(tmp_path / "gone")) is None


def test_the_fixtures_are_registered(pytester):
    result = pytester.runpytest("--fixtures")
    out = result.stdout.str()
    for name in ("ch32rv", "oep_host", "ch32_uart"):
        assert name in out


@pytest.mark.parametrize("knows_share, opens", [
    (True, [["oep.probe.share"]]),
    (False, [["oep.probe.share"], []]),
])
def test_oep_host_asks_the_broker_to_share_its_lock(monkeypatch, knows_share, opens):
    """A broker shares the lock of its tools with an open that carries oep.probe.share (host guide §7.1); an endpoint that
    does not know it refuses unsupported 0xFF, and the open goes again without it."""
    from oep_client import host as oh, link
    seen = []

    class FakeHost:
        def __init__(self, send):
            pass

        def open(self, lease_ms, *, owner=None, extensions=()):
            seen.append(list(extensions))
            if extensions and not knows_share:
                raise oh.Unsupported(types.SimpleNamespace(payload=b"\xff", describe=lambda: "unsupported 0xff"))

    fake_link = types.SimpleNamespace(send=None, attach_host=lambda h: None, close=lambda: None)
    monkeypatch.setattr(link, "TcpStream", lambda host, port: None)
    monkeypatch.setattr(link.SerialLink, "on_stream", staticmethod(lambda *a, **kw: fake_link))
    monkeypatch.setattr(oh, "Host", FakeHost)
    plugin._OepHost("127.0.0.1:1", "pytest t")
    assert seen == opens


def test_oep_host_passes_other_refusals_on(monkeypatch):
    from oep_client import host as oh, link

    class FakeHost:
        def __init__(self, send):
            pass

        def open(self, lease_ms, *, owner=None, extensions=()):
            raise oh.Unsupported(types.SimpleNamespace(payload=b"\x01", describe=lambda: "unsupported 0x01"))

    fake_link = types.SimpleNamespace(send=None, attach_host=lambda h: None, close=lambda: None)
    monkeypatch.setattr(link, "TcpStream", lambda host, port: None)
    monkeypatch.setattr(link.SerialLink, "on_stream", staticmethod(lambda *a, **kw: fake_link))
    monkeypatch.setattr(oh, "Host", FakeHost)
    with pytest.raises(oh.Unsupported):
        plugin._OepHost("127.0.0.1:1", "pytest t")
