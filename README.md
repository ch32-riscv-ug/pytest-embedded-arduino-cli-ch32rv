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
| `ch32_uart` | the DUT's UART through the WCH-Link behind the port (the Link's UART bridge, its CDC serial port): `ch32_uart.open(baud)` returns a channel with `expect` / `expect_exact` / `write`, like `dut` (pexpect underneath: the same keywords, a 30 s default timeout, `pexpect.TIMEOUT`) |

The fixtures and the device lock hook are the plugin's interface; the module's other names are internal.

OEP probes are [oep-client-python](https://pypi.org/project/oep-client-python/)'s, not this plugin's: its pytest plugin
(`pip install oep-client-python[pytest]`) gives `oep_host` and `oep_uart` and names the lock of an `oep://` port. On an
`oep://` port `ch32_uart` stops with an error pointing to `oep_uart`. Which DUT USART is wired to the Link is the
test's business, not the plugin's.

On a WCH-Link, `ch32_uart` and a `dut` read through the monitor's `uart` source share one serial port: use one or the
other in a test, not both.

The device lock (pytest-embedded-arduino-cli's `pytest_arduino_cli_device_lock_key`) of a WCH-Link is
`probe:<unit_id>`, the name the OEP family uses: the unit_id is the one ch32rv's broker gives the Link (its serial, lower
case), so `wchlink://<serial>`, the Link's serial port and `oep://<unit_id>?via=...` through ch32rv's broker take one
lock. `wchlink://usb-<topology>` has no serial in it and keeps the upstream rule's lock: name a Link the same way in
every run.

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
