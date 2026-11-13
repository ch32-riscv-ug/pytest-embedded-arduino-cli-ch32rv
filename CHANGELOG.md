# Changelog / 変更履歴

## Unreleased

## 0.0.9
- (EN) `oep_host` shares the broker's lock through the standard named extension `oep.probe.share` (OEP host guide §7.1) instead of `io.github.ch32-riscv-ug.share`, following ch32rv 6fdc7b5, which accepts only the standard one. Sharing needs that ch32rv or later; with an older broker the open falls back to a plain one (and a monitor running beside it holds the lock).
- (JA) `oep_host` は、ブローカーのロックへの相乗りに `io.github.ch32-riscv-ug.share` ではなく標準の名前つき拡張 `oep.probe.share`（OEP host ガイド §7.1）を使う。標準のものだけを受ける ch32rv 6fdc7b5 に合わせた。相乗りにはその ch32rv 以降が要り、それより前のブローカーでは拡張なしの open に落ちる（並んで動く monitor がロックを持っていれば取れない）。
- (EN) Bump dependencies to the latest: oep-client-python 0.0.54 and pytest-embedded-arduino-cli 1.12.0 as the lower bounds, the lock to pytest 9.2.0 and the rest; development and CI on Python 3.14; GitHub Actions checkout v7, setup-python v7, setup-uv v7, action-gh-release v3.
- (JA) 依存を最新に: oep-client-python 0.0.54 と pytest-embedded-arduino-cli 1.12.0 を下限に、lock は pytest 9.2.0 ほか最新に。開発と CI は Python 3.14。GitHub Actions は checkout v7、setup-python v7、setup-uv v7、action-gh-release v3。

## 0.0.8
- (EN) `oep_host` opens with ch32rv's named extension `io.github.ch32-riscv-ug.share`, so ch32rv's broker lets the session share the lock its monitor, flash and gdb hold (the dut's monitor runs beside the test); an endpoint that does not know the extension refuses it (unsupported 0xFF) and the open goes again without it. Needs ch32rv 2cea5d4 or later for the sharing; with an older broker the plain open is used. Requires oep-client-python 0.0.43 (`Host.open(extensions=...)`).
- (JA) `oep_host` は ch32rv の名前つき拡張 `io.github.ch32-riscv-ug.share` を付けて open する。ch32rv のブローカーは、その session を monitor・flash・gdb が持つロックに相乗りさせる（dut の monitor と並んで動く）。拡張を知らない相手は断る（unsupported 0xFF）ので、拡張なしで open し直す。相乗りには ch32rv 2cea5d4 以降が要り、それより前のブローカーでは拡張なしの open になる。oep-client-python 0.0.43（`Host.open(extensions=...)`）を下限に。
- (EN) Require oep-client-python 0.0.41, the release with the `oep://<probe>[/<port>[/<target>]][?via=<route>]` addresses.
- (JA) oep-client-python 0.0.41（`oep://<probe>[/<port>[/<target>]][?via=<経路>]` の住所が入った版）を下限に。

## 0.0.7
- (EN) Follow ch32rv's new addresses and JSON contract 5: the broker is asked with the bare address (`--probe <address>`; the `port:` prefix is refused now), `ch32_uart` reads the port of `oep://<probe>[/<port>[/<target>]][?via=<route>]` with the query taken off first, and a WCH-Link is matched by its `probe list` address too (`wchlink://usb-<topology>`). The branches for older ch32rv output (rows without `kind`, `endpoint` outside `result`, `any`) are gone.
- (JA) ch32rv の新しい住所と JSON の契約 5 に追従: ブローカーへは素の住所で聞く（`--probe <住所>`。`port:` の前置きは断られるようになった）。`ch32_uart` は `oep://<probe>[/<port>[/<target>]][?via=<経路>]` の口を、query を先に外してから読む。WCH-Link は `probe list` の address（`wchlink://usb-<topology>`）でも照合する。古い ch32rv の出力への分岐（`kind` の無い行、`result` の外の `endpoint`、`any`）は無くした。
- (EN) The fixtures are the plugin's interface; every other module name is internal (`_` prefixed). `oep_host` offers `.host` and `.touch()`. The `ch32_uart` channel is pexpect underneath and shaped like the `dut`: `expect` / `expect_exact` take a pattern or a list and the Dut's `expect_all`, `not_matching`, `return_what_before_match`, default to 30 s and raise `pexpect.TIMEOUT`.
- (JA) プラグインの接点は fixture だけにし、module のほかの名前は内部のもの（`_` 付き）にした。`oep_host` は `.host` と `.touch()` を持つ。`ch32_uart` の口は中が pexpect で `dut` と同じ形: `expect` / `expect_exact` はパターンかその一覧と、Dut の `expect_all`、`not_matching`、`return_what_before_match` を受け、既定の timeout は 30 秒、時間切れは `pexpect.TIMEOUT`。
- (EN) The device lock is keyed by the probe (pytest-embedded-arduino-cli's `pytest_arduino_cli_device_lock_key` hook, from 1.11.0): `ch32rv-probe:<id>`, the id an OEP probe's unit_id without its port, target and route, or a WCH-Link's USB serial, lower case. ch32rv's broker serves a WCH-Link as an OEP probe with that serial as unit_id, so `wchlink://<serial>` and `oep://<serial>?via=tcp:...` take one lock. A serial port path is mapped to the USB serial of its device, read from the OS's device list without opening the port (a WCH-Link's serial, a USB OEP probe's unit_id), so it takes the same lock as the probe's address; a USB-UART without a serial and `wchlink://usb-<topology>` keep the upstream key.
- (JA) 機器ロックの鍵を probe にした（pytest-embedded-arduino-cli の `pytest_arduino_cli_device_lock_key` hook。1.11.0 から）: `ch32rv-probe:<id>`。id は OEP の probe なら口・target・経路を除いた unit_id、WCH-Link なら USB の serial で、小文字。ch32rv のブローカーは WCH-Link をその serial を unit_id とする OEP の probe として出すので、`wchlink://<serial>` と `oep://<serial>?via=tcp:...` は 1 つのロックを取る。serial port の path は、port を開かずに OS の機器の一覧から読んだその機器の USB の serial（WCH-Link の serial、USB の OEP の probe の unit_id）に写すので、probe の住所と同じロックを取る。serial の無い USB-UART と `wchlink://usb-<topology>` は上流の鍵のまま。
- (EN) Lower bounds: pytest-embedded-arduino-cli 1.11.0 (the device lock key hook), oep-client-python 0.0.40 (labels with a target pin, `<port>.rx@pa10`); pexpect is a direct dependency.
- (JA) 下限: pytest-embedded-arduino-cli 1.11.0（機器ロックの鍵の hook）、oep-client-python 0.0.40（端子つきのラベル `<口>.rx@pa10`）。pexpect を直接の依存にした。
- (EN) README: on a WCH-Link, `ch32_uart` and the monitor's `uart` source share one serial port; `oep_host` waits up to 10 s for the broker.
- (JA) README: WCH-Link では `ch32_uart` と monitor の `uart` の source が 1 つの serial port を取り合うこと、`oep_host` がブローカーを最大 10 秒待つことを書いた。

## 0.0.6
- (EN) Follow OEP firmware 0.0.36, which moved the probe's settings into the core (fn 0's settings ops, `channel.{}.label`): `ch32_uart` reads the labels with oep-client-python 0.0.37's `settings.labels()` (now the lower bound; `oep_client.config` and `oep.probe.config` are gone). Every label - fixed, default and user - comes in one list, so the firmware's own are no longer passed separately. The hint for missing lines names the new command (`oep settings set <probe> core channel.<GPIO>.label=<port>.rx ... --save`).
- (JA) 設定を core へ移した OEP ファーム 0.0.36（fn 0 の settings、`channel.{}.label`）に追従: `ch32_uart` は oep-client-python 0.0.37 の `settings.labels()` でラベルを読む（これを下限に。`oep_client.config` と `oep.probe.config` は無くなった）。固定・既定・利用者のラベルが 1 つの一覧で来るので、firmware のラベルを別に渡すのをやめた。線が無いときの案内も新しいコマンド（`oep settings set <probe> core channel.<GPIO>.label=<口>.rx ... --save`）にした。

## 0.0.5
- (EN) Follow the reworked OEP spec (oep-spec 675288a; oep-client-python 0.0.33, now the lower bound): probes keep no saved plan, so `ch32_uart` on an OEP probe plans an `oep.fixture.uart` onto the port's `rx` / `tx` lines itself, found from the probe's labels (host guide §5.3: `<port>.rx` / `<port>.tx`; with one port also `rx` / `tx`, then the firmware's), and then configures it. The port is the `<port>` of an `oep://<probe>/<port>` test port; a probe that names several ports without one stops with an error asking for it, and missing lines stop with one asking for the labels (`oep config label <probe> <ch> <port>.rx --save`). The plan is the session's and ends with it.
- (JA) 作り直された OEP 仕様（oep-spec 675288a。oep-client-python 0.0.33 を下限に）に追従: probe は plan を保存しないので、OEP の probe の `ch32_uart` は probe のラベルから口の `rx` / `tx` の線を引き（host ガイド §5.3: `<口>.rx` / `<口>.tx`。口が 1 つなら `rx` / `tx`、最後に firmware のもの）、`oep.fixture.uart` をそこへ自分で plan してから configure する。口は試験の port `oep://<probe>/<口>` の `<口>`。口を複数名付けた probe で口の指定が無ければそれを求めるエラーで、線が無ければラベルを求めるエラー（`oep config label <probe> <ch> <口>.rx --save`）で止まる。plan は session のもので、session とともに終わる。

## 0.0.4
- (EN) `ch32_uart` reads only the WCH-Link rows of ch32rv's `probe list` (`kind: "wchlink"`, or no `kind` before ch32rv 0.13.2): the OEP probes that list now carries have their CDC in `ports` too, and that port is the OEP link, not a UART bridge.
- (JA) `ch32_uart` は ch32rv の `probe list` の WCH-Link の行（`kind: "wchlink"`、ch32rv 0.13.2 より前は `kind` 無し）だけを読む。一覧に入るようになった OEP の probe も `ports` に CDC を持つが、それは OEP のリンクで UART bridge ではない。
- (EN) The test's port comes off pytest-embedded-arduino-cli's monitor wrapper through its `MonitorTarget` (public API since 1.8.0, now the lower bound) instead of this plugin slicing the `arduinomonitor://` string, whose spelling is not a contract.
- (JA) 試験の port は pytest-embedded-arduino-cli の `MonitorTarget`（1.8.0 から公開 API、下限もそこへ）で monitor の包みを外す。`arduinomonitor://` の文字列をこのプラグインが切っていたのをやめた（綴りは契約ではない）。

## 0.0.3
- (EN) `oep_host` waits up to 10 s for the broker the dut's monitor starts, instead of failing when a test asks for it before anything was read through the monitor.
- (JA) `oep_host` は dut の monitor が起こすブローカーを最大 10 秒待つ。monitor から何も読む前に試験が求めると失敗していた。

## 0.0.2
- (EN) Require oep-client-python 0.0.5, the version the fixtures are tested with (its USB exit fix does not touch `oep_host`, which reaches the probe through ch32rv's broker over TCP).
- (JA) oep-client-python 0.0.5 を必須に（fixture を確かめた版）。0.0.5 の USB の終了の直しは、ch32rv のブローカーへ TCP でつなぐ `oep_host` には関わらない。

## 0.0.1
- (EN) First beta. Three fixtures for pytest-embedded-arduino-cli tests on CH32 boards flashed by ch32rv: `ch32rv` (the platform's ch32rv, from `runtime.tools.ch32rv.path`), `oep_host` (an oep-client-python session on the OEP probe behind the test's port, through ch32rv's broker, with a 60 s lease refreshed on use), and `ch32_uart` (the DUT's UART as the probe sees it - a WCH-Link's UART bridge or an OEP probe's fixture UART - opened with `open(baud)` and read with `expect` / `expect_exact` / `write`, like `dut`).
- (JA) 最初のβ版。ch32rv で書く CH32 の板の pytest-embedded-arduino-cli の試験のための 3 つの fixture: `ch32rv`（platform の ch32rv、`runtime.tools.ch32rv.path` から）、`oep_host`（試験の port の先の OEP の probe への oep-client-python の session。ch32rv のブローカー経由、60 秒の lease を使うたびに延ばす）、`ch32_uart`（probe から見た DUT の UART。WCH-Link の UART bridge か OEP の probe の fixture UART を `open(baud)` で開き、`dut` と同じ `expect` / `expect_exact` / `write` で扱う）。
