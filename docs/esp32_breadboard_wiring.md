# ESP32 ブレッドボード計測設計

## 1. 今回の前提

最初の室温ベンチ試験は次の構成で行う。

- ESP32-DevKitC V4 または同等の ESP32-WROOM-32 開発ボード
- SHT45 のブレークアウト基板（裸の DFN センサーではない）x1
- DS18B20 の3線式防水プローブ x1（ESP32筐体温度の安全監視）
- フルサイズのブレッドボード、ジャンパ線、4.7 kOhm 抵抗 x1
- データ通信対応 USB ケーブル、テスター

ESP32-C3、S3、S2 は GPIO 番号とブート条件が異なるため、この配線表をそのまま
使わない。ボード上のシルク印刷が `3V3`, `GND`, `GPIO21`, `GPIO22`, `GPIO27`
であることを先に確認する。

## 2. 採用ピン

| 用途 | ESP32 ピン | 理由 |
|---|---|---|
| I2C SDA | GPIO21 | DevKitCで使用しやすく、ブートストラップピンではない |
| I2C SCL | GPIO22 | DevKitCで使用しやすく、ブートストラップピンではない |
| DS18B20 DQ | GPIO27 | 通常GPIOで、I2C・USB UARTと競合しない |
| センサー電源 | 3V3 | SHT45とESP32の論理レベルを3.3 Vに統一 |
| 共通基準 | GND | 全センサーとESP32で共通化 |

GPIO0, 2, 5, 12, 15 は ESP32 のストラップピンなので初期配線では使わない。
GPIO6-11 はフラッシュ用、GPIO1/3 は USB-UART 用のため避ける。

## 3. 配線表

### 3.1 SHT45 ブレークアウト

| SHT45基板表記 | 接続先 |
|---|---|
| `VIN`, `VCC`, `3V3` のいずれか | ESP32 `3V3` |
| `GND` | ESP32 `GND` |
| `SDA` | ESP32 `GPIO21` |
| `SCL` | ESP32 `GPIO22` |

ブレークアウト基板に I2C プルアップが実装済みなら追加しない。実装有無が不明なら、
基板型番または回路図を確認する。裸センサー相当でプルアップが無い場合のみ、SDA と
SCL の各線から 3V3 へ 4.7 kOhm を追加する。裸の SHT45 は最大電源電圧が 3.6 V
なので 5 V へ接続しない。

### 3.2 DS18B20（3線式）

ケーブル色は製品により異なるため、色だけで決めず購入品の仕様書を優先する。

| DS18B20信号 | 一般的な色 | 接続先 |
|---|---|---|
| VDD | 赤 | ESP32 `3V3` |
| GND | 黒 | ESP32 `GND` |
| DQ/Data | 黄または白 | ESP32 `GPIO27` |
| 4.7 kOhm抵抗 | - | `GPIO27` と `3V3` の間 |

寄生電源モードは使わず、VDD・GND・DQ の3線で接続する。

## 4. ブレッドボード配置

```text
USB
 │
 ┌──────────────── ESP32 DevKitC ────────────────┐
 │ 3V3   GND           GPIO21 GPIO22 GPIO27      │
 └──┬─────┬──────────────┬──────┬──────┬─────────┘
    │     │              │      │      │
  +3.3V  GND             │      │      ├──── DS18B20 DQ
  rail   rail            │      │      │
    │     │              │      │     [4.7k]
    │     │              │      │      │
    │     │              │      │     +3.3V
    │     │              │      │
    │     └── SHT45 GND  │      └──── SHT45 SCL
    └──────── SHT45 VCC  └─────────── SHT45 SDA
    │     │
    └──── DS18B20 VDD
          DS18B20 GND ──────────────── GND rail
```

ESP32はブレッドボード中央の溝をまたぐ向きに置く。電源レールが途中で分断されている
ブレッドボードでは、左右または上下のレールをジャンパ線で接続する。USBを挿す前に、
3V3-GND間の短絡がないことをテスターで確認する。

## 5. 電源投入の順序

1. USBを抜いた状態で配線する。
2. センサーを外し、ESP32単体をUSB接続して `3V3-GND` が約3.3 Vか確認する。
3. USBを抜き、SHT45だけを接続する。
4. USB接続後、I2C scan で `0x44` が1個だけ見えることを確認する。
5. USBを抜き、DS18B20と4.7 kOhm抵抗を追加する。
6. OneWire scan で8 byteのROM IDが1個見えることを確認する。
7. 両センサーを2秒周期で30分記録し、欠測・CRCエラー・リセットがないか確認する。

電源はUSB、5Vピン、3V3ピンのいずれか1系統だけを使う。USB接続中に外部電源を
5V/3V3ピンへ同時投入しない。

## 6. MicroPythonでの確認

### 6.1 I2C scan

```python
from machine import I2C, Pin

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=100_000)
print([hex(address) for address in i2c.scan()])
# 期待値: ['0x44']
```

### 6.2 DS18B20 scan

```python
from machine import Pin
import ds18x20
import onewire

bus = onewire.OneWire(Pin(27))
sensor = ds18x20.DS18X20(bus)
print(sensor.scan())
# 期待値: 8 byteのROM IDが1個
```

### 6.3 SHT45の読取条件

- I2Cアドレス: `0x44`
- 高精度測定コマンド: `0xFD`
- コマンド送信後に10 ms待ち、6 byteを読む
- 温度2 byte + CRC、湿度2 byte + CRC の両方をCRC-8で検証する
- CRC polynomial `0x31`、初期値 `0xFF`
- 変換式: `T = -45 + 175 * raw / 65535`
- 変換式: `RH = -6 + 125 * raw / 65535`、保存時は0-100 %へ制限

## 7. ESP32からPCへの取り方

最初はWi-Fiを使わず、USBシリアルを正本とする。Wi-Fi切断、時刻同期、再送処理を
持ち込まないため、ベンチ試験の切り分けが簡単になる。

ESP32は2秒ごとにJSON Linesを1行出力する。

```json
{"time_s": 2.0, "sensor_id": "SHT45-LOWER", "temp_c": 24.81, "rh_pct": 46.2, "box_temp_c": 25.0, "status": "ok"}
```

PC側では Thonny、mpremote、シリアルモニターを閉じ、COMポートを1つのプロセスだけで
開く。

```powershell
saunaflow-daq log --port COM5 --baudrate 115200 --duration 1800 `
  --output experiments/raw/esp32_bench_001_raw.csv
```

記録後にメタデータを作成し、検証してからprocessed CSVへ変換する。

```powershell
saunaflow-daq meta experiments/raw/esp32_bench_001_raw.csv `
  --session-id esp32-bench-001 --sensor-id SHT45-LOWER --sensor-type SHT45 `
  --output experiments/meta/esp32_bench_001_meta.yaml

saunaflow-daq validate-meta experiments/meta/esp32_bench_001_meta.yaml

saunaflow-daq process experiments/raw/esp32_bench_001_raw.csv `
  --meta experiments/meta/esp32_bench_001_meta.yaml
```

## 8. 合否判定

最初のブレッドボード試験は次をすべて満たしたら合格とする。

- 起動10回でI2Cアドレス `0x44` を10回認識する。
- DS18B20のROM IDが毎回同じである。
- 30分で期待サンプル数900件の99%以上を記録する。
- SHT45 CRCエラーが0件である。
- ESP32の再起動、USB切断、`sensor_error` が0件である。
- 室温でSHT45とDS18B20の温度差が概ね2 degC以内である。

## 9. サウナ投入前の制約

- ブレッドボード、ESP32、USBコネクタはサウナ室へ入れない。
- SHT45ブレークアウト全体の耐熱は、SHT45素子単体の定格と同じとは限らない。
- 結露状態で通電しない。ロウリュ直後の水滴を直接センサーへ当てない。
- ブレッドボードのI2C配線は20 cm程度までを初期目安とする。
- 長いセンサーケーブルは100 kHz化、GNDとの撚り、バス容量確認が必要になる。
- SHT45は通常 `0x44` 固定なので、同一アドレス品を2台使う場合はI2Cマルチプレクサ、
  別I2Cバス、または異なるアドレス品を設計する。

## 10. 参照仕様

- [Espressif ESP32-DevKitC V4 User Guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- [Espressif ESP32 GPIO reference](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32/api-reference/peripherals/gpio.html)
- [Sensirion SHT4x datasheet](https://sensirion.com/media/documents/33FD6951/6555C40E/Sensirion_Datasheet_SHT4x.pdf)
- [Analog Devices DS18B20 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ds18b20.pdf)
- [MicroPython ESP32 quick reference](https://docs.micropython.org/en/v1.25.0/esp32/quickref.html)
