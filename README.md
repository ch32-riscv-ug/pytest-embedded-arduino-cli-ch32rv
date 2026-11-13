# pytest-embedded-arduino-cli-ch32rv

[Japanese](README.ja.md)

A [pytest-embedded-arduino-cli](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli) plugin for CH32 boards
flashed by [ch32rv](https://github.com/ch32-riscv-ug/ch32rv) (the uploader the
[ArduinoCore-CH32RV](https://github.com/ch32-riscv-ug/ArduinoCore-CH32RV) platform bundles).

pytest-embedded-arduino-cli already uploads with ch32rv and gives the test a `dut` read through ch32rv's monitor (pick
its `source` - `uart`, `dmseq`, ... - with the profile's `port_config` in `sketch.yaml`). This plugin adds:

| fixture | what it is |
|---|---|
| `ch32rv` | the ch32rv the platform installed (`runtime.tools.ch32rv.path`), as a path |
| `oep_host` | an [oep-client-python](https://pypi.org/project/oep-client-python/) session on the OEP probe behind the port, through ch32rv's broker: `.host` is the Host, `.touch()` keeps the lease |
| `ch32_uart` | the DUT's UART as the probe sees it: `ch32_uart.open(baud)` returns a channel with `expect` / `expect_exact` / `write`, like `dut` (pexpect underneath: the same keywords, a 30 s default timeout, `pexpect.TIMEOUT`) |

The fixtures are the plugin's interface; the module's other names are internal.

`ch32_uart` opens a WCH-Link's UART bridge (the CDC serial port of the Link behind the port), or on an OEP probe an
`oep.fixture.uart` planned onto the port's `rx` / `tx` lines, found from the labels the probe keeps (OEP host guide
§5.3: `<port>.rx` / `<port>.tx`, e.g. `oep settings set <probe> core channel.GPIO22.label=v003.rx --save`). The port is the `<port>` of an
`oep://<probe>/<port>[?via=<route>]` test port; a probe that names several ports needs that. Which DUT USART and route
are wired to the probe is the test's business, not the plugin's.

On a WCH-Link, `ch32_uart` and a `dut` read through the monitor's `uart` source share one serial port: use one or the
other in a test, not both.

pytest-embedded-arduino-cli's device lock takes one key per probe (`ch32rv-probe:<unit_id or USB serial>`), whether
the port names it by `oep://`, `wchlink://<serial>` or its serial port. A probe behind a USB-UART with no serial (an
ESP32 on a CH340) cannot be matched to its `oep://` address: name it the same way in every run.

`oep_host` waits up to 10 s for the broker the dut's monitor starts. Its session shares the lock of ch32rv's own tools (the
monitor, flash, gdb) through the open extension `oep.probe.share` (OEP host guide §7.1). The OEP session holds a 60 s lease, refreshed
whenever the test uses it; a test that stays quiet for longer loses it.

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
