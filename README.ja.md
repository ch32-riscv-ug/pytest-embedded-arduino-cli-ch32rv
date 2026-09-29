# pytest-embedded-arduino-cli-ch32rv

[English](README.md)

[ch32rv](https://github.com/ch32-riscv-ug/ch32rv)（[ArduinoCore-CH32](https://github.com/ch32-riscv-ug/ArduinoCore-CH32)
が同梱する書き込みツール）で書く CH32 の板のための、[pytest-embedded-arduino-cli](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli)
のプラグイン。

pytest-embedded-arduino-cli は ch32rv で書き込み、ch32rv の monitor で読む `dut` を出す（`source` の `uart` / `dmseq` などは
`sketch.yaml` の profile の `port_config` で選ぶ）。このプラグインが足すもの:

| fixture | 中身 |
|---|---|
| `ch32rv` | platform が入れた ch32rv（`runtime.tools.ch32rv.path`）の path |
| `oep_host` | port の先の OEP の probe への [oep-client-python](https://pypi.org/project/oep-client-python/) の session。ch32rv のブローカー経由（`.host` が Host） |
| `ch32_uart` | probe から見た DUT の UART。`ch32_uart.open(baud)` が `dut` と同じ `expect` / `expect_exact` / `write` を持つ口を返す |

`ch32_uart` は、WCH-Link なら port の先の Link の UART bridge（CDC の serial port）を、OEP の probe なら、probe に保存した plan
がピンを割り当てた `oep.fixture.uart` を開く（`oep config plan <probe> oep.fixture.uart#<n> rx=<ch> tx=<ch> --save`）。DUT のどの
USART と route が probe につながっているかは試験の側が知っていることで、プラグインは知らない。

OEP の session は 60 秒の lease を持ち、試験が使うたびに延ばす。それより長く黙っている試験では session が切れる。

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
