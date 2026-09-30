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
    assert plugin.dut_address(config_with_port(port)) == address


def test_dut_address_without_a_port_is_a_usage_error():
    with pytest.raises(pytest.UsageError):
        plugin.dut_address(config_with_port(None))


def channel(chunks):
    sent = []
    it = iter(chunks)
    return plugin.Channel(lambda: next(it, b""), sent.append, "test"), sent


def test_channel_expect_and_expect_exact_consume_up_to_the_match():
    ch, sent = channel([b"hello from ", b"ch32\r\nint=42\r\n", b"hex=BEEF\r\n"])
    assert ch.expect_exact("hello from ch32") == b"hello from ch32"
    assert ch.expect(r"int=(\d+)").group(1) == b"42"
    assert ch.expect_exact("hex=BEEF")
    ch.write("RUN\n")
    assert sent == [b"RUN\n"]


def test_channel_expect_times_out_with_the_tail_in_the_message():
    ch, _ = channel([b"garbage"])
    with pytest.raises(TimeoutError, match="garbage"):
        ch.expect_exact("never", timeout=0.1)


# ch32rv `probe list`: rows without `kind` (up to 0.13.1) are WCH-Links; from 0.13.2 every row has a
# `kind` and the OEP probes ch32rv enumerates over USB are there too, their CDC (the OEP link itself,
# not a UART bridge) in `ports`.
PROBES = {"result": {"probes": [
    {"serial": "FBC18F0680B0", "ports": ["/dev/ttyACM3"]},
    {"serial": "434A124C5596", "ports": ["/dev/ttyACM1"], "kind": "wchlink"},
    {"serial": "9489dd2ae0953650", "ports": ["/dev/ttyACM5"], "kind": "oep", "model": "OEP probe (RP2350)"},
]}}


@pytest.mark.parametrize("address, bridge", [
    ("wchlink://FBC18F0680B0", "/dev/ttyACM3"),
    ("/dev/ttyACM1", "/dev/ttyACM1"),
    ("wchlink://434A124C5596", "/dev/ttyACM1"),
    ("oep://30eda0e31108-hs/x035", None),
    ("oep://9489dd2ae0953650/l103", None),
    ("/dev/ttyACM5", None),
    ("/dev/ttyUSB0", None),
])
def test_wch_link_uart_maps_the_port_to_the_links_bridge(monkeypatch, address, bridge):
    monkeypatch.setattr(plugin, "run_ch32rv", lambda ch32rv, *args, **kw: PROBES)
    assert plugin.wch_link_uart("ch32rv", address) == bridge


def test_the_fixtures_are_registered(pytester):
    result = pytester.runpytest("--fixtures")
    out = result.stdout.str()
    for name in ("ch32rv", "oep_host", "ch32_uart"):
        assert name in out
