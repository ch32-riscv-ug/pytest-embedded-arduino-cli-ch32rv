# Changelog / 変更履歴

## Unreleased

## 0.0.1
- (EN) First beta. Three fixtures for pytest-embedded-arduino-cli tests on CH32 boards flashed by ch32rv: `ch32rv` (the platform's ch32rv, from `runtime.tools.ch32rv.path`), `oep_host` (an oep-client-python session on the OEP probe behind the test's port, through ch32rv's broker, with a 60 s lease refreshed on use), and `ch32_uart` (the DUT's UART as the probe sees it - a WCH-Link's UART bridge or an OEP probe's fixture UART - opened with `open(baud)` and read with `expect` / `expect_exact` / `write`, like `dut`).
- (JA) 最初のβ版。ch32rv で書く CH32 の板の pytest-embedded-arduino-cli の試験のための 3 つの fixture: `ch32rv`（platform の ch32rv、`runtime.tools.ch32rv.path` から）、`oep_host`（試験の port の先の OEP の probe への oep-client-python の session。ch32rv のブローカー経由、60 秒の lease を使うたびに延ばす）、`ch32_uart`（probe から見た DUT の UART。WCH-Link の UART bridge か OEP の probe の fixture UART を `open(baud)` で開き、`dut` と同じ `expect` / `expect_exact` / `write` で扱う）。
