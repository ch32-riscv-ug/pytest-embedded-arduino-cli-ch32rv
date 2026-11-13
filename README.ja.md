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
| `oep_host` | port の先の OEP の probe への [oep-client-python](https://pypi.org/project/oep-client-python/) の session。ch32rv のブローカー経由。`.host` が Host、`.touch()` が lease を延ばす |
| `ch32_uart` | probe から見た DUT の UART。`ch32_uart.open(baud)` が `dut` と同じ `expect` / `expect_exact` / `write` を持つ口を返す（中は pexpect: 同じキーワード、既定の timeout 30 秒、`pexpect.TIMEOUT`） |

プラグインの接点は fixture だけで、module のほかの名前は内部のもの。

`ch32_uart` は、WCH-Link なら port の先の Link の UART bridge（CDC の serial port）を、OEP の probe なら、probe が持つラベルから
口の `rx` / `tx` の線を引き（OEP host ガイド §5.3: `<口>.rx` / `<口>.tx`。例 `oep settings set <probe> core channel.GPIO22.label=v003.rx --save`）、そこへ
plan した `oep.fixture.uart` を開く。口は試験の port `oep://<probe>/<口>[?via=<経路>]` の `<口>` で、口を複数名付けた probe では
それが要る。DUT のどの USART と route が probe につながっているかは試験の側が知っていることで、プラグインは知らない。

WCH-Link では、`ch32_uart` と monitor の `uart` の source で読む `dut` が 1 つの serial port を取り合う。1 つの試験ではどちらか一方を使う。

pytest-embedded-arduino-cli の機器ロックは、port が `oep://`、`wchlink://<serial>`、serial port のどれで名指しても、probe ごとに 1 つの鍵
（`ch32rv-probe:<unit_id か USB の serial>`）を取る。serial の無い USB-UART の先の probe（CH340 の先の ESP32 など）は `oep://` の住所と
結び付けられないので、どの実行でも同じ書き方で名指す。

`oep_host` は dut の monitor が起こすブローカーを最大 10 秒待つ。その session は、open の拡張
`oep.probe.share`（OEP host ガイド §7.1）で、ch32rv の道具（monitor、flash、gdb）のロックに相乗りする。OEP の session は 60 秒の lease を持ち、試験が使うたびに延ばす。
それより長く黙っている試験では session が切れる。

```sh
pip install pytest-embedded-arduino-cli-ch32rv
```
