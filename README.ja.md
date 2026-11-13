# pytest-embedded-arduino-cli-ch32rv

[English](README.md)

[ch32rv](https://github.com/ch32-riscv-ug/ch32rv)（[ArduinoCore-CH32RV](https://github.com/ch32-riscv-ug/ArduinoCore-CH32RV)
が同梱する書き込みツール）で書く CH32 の板のための、[pytest-embedded-arduino-cli](https://github.com/tanakamasayuki/pytest-embedded-arduino-cli)
のプラグイン。

pytest-embedded-arduino-cli は ch32rv で書き込み、ch32rv の monitor で読む `dut` を出す（`source` の `uart` / `dmseq` などは
`sketch.yaml` の profile の `port_config` で選ぶ）。このプラグインが足すもの:

| fixture | 中身 |
|---|---|
| `ch32rv` | platform が入れた ch32rv（`runtime.tools.ch32rv.path`）の path |
| `ch32_uart` | port の先の WCH-Link を通した DUT の UART（Link の UART bridge、CDC の serial port）。`ch32_uart.open(baud)` が `dut` と同じ `expect` / `expect_exact` / `write` を持つ口を返す（中は pexpect: 同じキーワード、既定の timeout 30 秒、`pexpect.TIMEOUT`） |

プラグインの接点は fixture と機器ロックの hook だけで、module のほかの名前は内部のもの。

OEP の probe はこのプラグインではなく [oep-client-python](https://pypi.org/project/oep-client-python/) のもの。その pytest プラグイン
（`pip install oep-client-python[pytest]`）が `oep_host` と `oep_uart` を出し、`oep://` の port のロックの名前を返す。`oep://` の port で
`ch32_uart` を使うと、`oep_uart` を案内するエラーで止まる。DUT のどの USART が Link につながっているかは試験の側が知っていることで、
プラグインは知らない。

WCH-Link では、`ch32_uart` と monitor の `uart` の source で読む `dut` が 1 つの serial port を取り合う。1 つの試験ではどちらか一方を使う。

WCH-Link の機器ロック（pytest-embedded-arduino-cli の `pytest_arduino_cli_device_lock_key`）の名前は、OEP の系統と同じ `probe:<unit_id>`。
unit_id は ch32rv のブローカーが Link に付けるもの（serial を小文字にしたもの）なので、`wchlink://<serial>`、Link の serial port、
ch32rv のブローカー経由の `oep://<unit_id>?via=...` は 1 つのロックを取る。`wchlink://usb-<topology>` には serial が入っていないので
上流の規則のロックのまま。どの実行でも Link を同じ書き方で名指す。

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
