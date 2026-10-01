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
| `oep_host` | an [oep-client-python](https://pypi.org/project/oep-client-python/) session on the OEP probe behind the port, through ch32rv's broker (`.host` is the Host) |
| `ch32_uart` | the DUT's UART as the probe sees it: `ch32_uart.open(baud)` returns a channel with `expect` / `expect_exact` / `write`, like `dut` |

`ch32_uart` opens a WCH-Link's UART bridge (the CDC serial port of the Link behind the port), or on an OEP probe the
`oep.fixture.uart` whose pins the probe's saved plan assigns (`oep config plan <probe> oep.fixture.uart#<n> rx=<ch>
tx=<ch> --save`). Which DUT USART and route are wired to the probe is the test's business, not the plugin's.

The OEP session holds a 60 s lease, refreshed whenever the test uses it; a test that stays quiet for longer loses it.

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
