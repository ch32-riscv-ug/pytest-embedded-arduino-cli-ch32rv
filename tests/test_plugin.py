"""Board-free checks of the plugin: the parts that do not need a probe."""
import types

import pytest

from pytest_embedded_arduino_cli_ch32rv import plugin

pytest_plugins = ["pytester"]


def config_with_port(port):
    return types.SimpleNamespace(getoption=lambda name, default=None: port if name == "port" else default)


@pytest.mark.parametrize("port, address", [
    ("/dev/ttyACM3", "/dev/ttyACM3"),
    ("wchlink://FBC18F0680B0", "wchlink://FBC18F0680B0"),
    ("arduinomonitor:///dev/ttyACM3?sketch=%2Ftmp%2Fx&profile=ch32v203", "/dev/ttyACM3"),
    ("arduinomonitor://oep%3A%2F%2F30eda0e31108-hs%2Fx035?profile=ch32x035", "oep://30eda0e31108-hs/x035"),
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


PROBES = {"result": {"probes": [
    {"serial": "FBC18F0680B0", "ports": ["/dev/ttyACM3"]},
    {"serial": "434A124C5596", "ports": ["/dev/ttyACM1"]},
]}}


@pytest.mark.parametrize("address, bridge", [
    ("wchlink://FBC18F0680B0", "/dev/ttyACM3"),
    ("/dev/ttyACM1", "/dev/ttyACM1"),
    ("oep://30eda0e31108-hs/x035", None),
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
