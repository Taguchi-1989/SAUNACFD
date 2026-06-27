# 実機計測 — ハードウェア配線・構成ガイド (DAQ build guide)

**作成日**: 2026-06-27
**対象読者**: 部品は購入済みだが配線・組み立てがこれからの人
**関連**: `docs/procurement_plan.md`(何を買うか) / `docs/measurement_implementation_plan.md`(いつ・どう測るか) / `firmware/`(マイコン側コード) / `src/daq/`(ホスト側コード)

> このドキュメントは「買った部品をどう繋ぎ、どう起動して、データがCSVになるまで」だけに集中する。手順どおりに進めれば、サウナに入れる前に**机上(ベンチ)で end-to-end が通る**ところまで行ける。

---

## 0. まず用語の整理（ここが混乱の元）

「ラズパイ」には2種類あり、本プロジェクトでは**役割が違う**。

| 呼称 | 正式名 | 本構成での役割 | 例 |
|------|--------|----------------|----|
| **Pico / ピコ** | Raspberry Pi **Pico** WH | センサーを読む**マイコン（センサーノード）**。室内側。 | RP2040, MicroPython |
| **ラズパイ本体** | Raspberry Pi **4 / 5 / Zero 2 W** | Picoから来たデータを**CSVに記録するホスト**。室外側。PCの代わり。 | Linux SBC |

- 既存コード(`firmware/`, `src/daq/serial_logger.py`)は **「Pico がセンサーを読み → USBシリアルで JSON 行を送り → ホスト(ラズパイ本体 or PC)が CSV 化」** という二段構成を前提にしている。
- 「ラズパイで取りたい」は通常**ホスト＝ラズパイ本体**を指す（ノートPCを常設しなくて済む）。本ガイドはこれを**標準構成（構成A）**とする。
- Pico を使わず**ラズパイ本体の GPIO に直接センサーを挿す**やり方もある（**構成B**）。配線は減るが Pi 側に小さなリーダ実装が要る。§7参照。

---

## 1. 全体構成図（構成A：標準 / Pico＋ラズパイ）

```text
        [サウナ室内・高温]                    [室外・常温]
 ┌───────────────────────────┐
 │  温湿度センサー (空気中に吊る)         │
 │   DHT22 もしくは SHT45              │
 │        │ 信号線(耐熱シリコン線 1-2m)   │
 │        ▼                          │        USB (microB, 3-5m, データ対応)
 │  ┌──────────────┐ ─────────────────┼──────────────────────────► ┌───────────────┐
 │  │  Pico WH      │                  │                            │ ラズパイ本体    │
 │  │ (断熱ボックス内)│                  │                            │  or ノートPC   │
 │  │  + DS18B20    │ ← 箱内温度監視     │                            │ serial_logger  │
 │  └──────────────┘                  │                            └───────┬───────┘
 │   保冷剤(袋+タオルで隔離)             │                                    │
 └───────────────────────────┘                                    ▼
                                                          experiments/raw/*.csv
                                                                   │
                                  process → validation → reporting (既存パイプライン)
```

**設計原則（procurement_plan より）**: 熱に弱い電子部品（Pico・基板・コネクタ・はんだ）はサウナ空気に晒さない。**測りたい空気に触れるセンサー素子だけ**を信号線で外に出す。Pico は床面/ドア近傍の断熱ボックスに入れ、箱内温度を DS18B20 で監視（60℃でシャットダウン）。

---

## 2. データ契約（配線が「正しい」と言える条件）

配線とコードは次の1行で繋がっている。Pico がこの JSON 行を 2 秒ごとに USB に吐き、ホストがそれを CSV にする。

```json
{"time_s": 0.0, "temp_c": 68.5, "rh_pct": 12.3, "box_temp_c": 25.1, "status": "ok"}
```

| フィールド | 由来センサー | 単位 | 異常時 |
|-----------|------------|------|--------|
| `time_s` | Pico内部時計 | s | — |
| `temp_c` | 温湿度センサー(室内空気) | ℃ | 読み失敗で `-999.0` |
| `rh_pct` | 温湿度センサー | %RH | 読み失敗で `-999.0` |
| `box_temp_c` | DS18B20(箱内) | ℃ | センサ無しで `-999.0` |
| `status` | `box_temp_c`から判定 | — | `ok`<50℃ / `warn`≥50℃ / `shutdown`≥60℃ |

定義元: `firmware/main.py`, `src/daq/serial_logger.py`(`RAW_CSV_FIELDS`)。**配線を変えても、この JSON が出ていれば後段は無変更で動く。**

---

## 3. Pico WH ピン配置（既存ファームウェアの設定 = そのまま動く）

`firmware/config.py` の割り当てに**完全一致**させること。変えたいときは config.py を直す。

| 信号 | config.py | Pico GP | Pico 物理ピン | 備考 |
|------|-----------|---------|--------------|------|
| DHT22 データ | `DHT22_PIN = 15` | GP15 | **20番ピン** | 室内空気センサー |
| DS18B20 データ | `DS18B20_PIN = 14` | GP14 | **19番ピン** | 箱内温度監視 |
| 3.3V 電源 | — | 3V3(OUT) | **36番ピン** | 両センサーのVCC |
| GND | — | GND | **38番ピン**(他に3/8/13/18/23/28/33) | 両センサーのGND |
| USB | — | microB | 基板端コネクタ | ホストへ |

> Pico のピン番号は基板の**端から数える物理番号**。GP番号(論理)と物理番号は違うので注意（例: GP15=物理20番）。

### 3.1 DHT22 配線（3本）— **今すぐ動く構成**

DHT22 は単線デジタル。3ピンモジュール（プルアップ内蔵が多い）なら抵抗不要。素の AM2302(4ピン)はデータ線にプルアップが要る。

```text
  DHT22 module            Pico WH
  ┌─────────┐
  │  +(VCC) │────────────► 3V3(OUT)  [物理36]
  │  OUT    │────────────► GP15      [物理20]
  │  -(GND) │────────────► GND       [物理38]
  └─────────┘
   ※素のAM2302(4ピン)の場合: VCC–DATA 間に 4.7kΩ〜10kΩ のプルアップを追加
   ※延長は3m以内。長いとプルアップを4.7kΩ寄りに。
```

- 適合温度: −40〜**80℃**。Phase1 の lower_bench(≈54℃)・floor_level(≈31℃) は範囲内 → **DHT22 で測れる**。
- upper_bench(≈95℃)は仕様外 → §6 の K型熱電対へ。

### 3.2 DS18B20 配線（箱内温度・3本）

```text
  DS18B20(防水)           Pico WH
   赤 VDD ───────────────► 3V3(OUT)  [物理36]
   黄 DATA ──────┬────────► GP14      [物理19]
   黒 GND ───────│────────► GND       [物理38]
                 │
            4.7kΩ プルアップ
          (DATA–VDD 間に必須)
```

- **DS18B20 はプルアップ 4.7kΩ が必須**（1-Wire の仕様）。Gravity/アダプタ付きキットなら基板に内蔵されていることが多い→その場合は追加不要。
- 箱内に置く（空気中ではなくボックス内温度の監視用）。

### 3.3 SHT45 / SHT35 配線（I2C・4本）— **高温対応・将来 or 既に買った人向け**

procurement では DHT22 より高温余裕のある SHT45/SHT35(I2C, −40〜125℃) を推奨。配線は I2C 4 本。

```text
  SHT45 (STEMMA QT/Qwiic)   Pico WH
   VIN/3V3 ──────────────► 3V3(OUT)  [物理36]
   GND ──────────────────► GND       [物理38]
   SDA ──────────────────► GP4 (I2C0 SDA) [物理6]
   SCL ──────────────────► GP5 (I2C0 SCL) [物理7]
   ※STEMMA QT/Qwiic モジュールは I2C プルアップ内蔵 → 追加抵抗不要
   ※I2Cは長距離に弱い。延長は2m以内、できれば1m。
```

> ⚠️ **重要（未実装）**: 既存 `firmware/` には **SHT45 ドライバが無い**（`firmware/sensors/` は dht22.py と ds18b20.py のみ）。SHT45 を使うには
> 1. `firmware/sensors/sht45.py`(I2C 0x44, コマンド 0xFD, CRC8 検証) を追加
> 2. `firmware/config.py` に `I2C_SDA=4, I2C_SCL=5` を追加
> 3. `firmware/main.py` の `DHT22Sensor` を `SHT45Sensor` に差し替え
> が必要。出力 JSON 契約(§2)は同じなのでホスト側(`src/daq/`)は無変更。**このドライバ追加は別タスク**として切り出す（本ガイドは配線まで）。
> SHT45 を 2 個同一 I2C バスに付ける場合、アドレスが 0x44 固定で衝突するため I2C マルチプレクサ(TCA9548A)か 2 本目を別バスにする必要がある。まずは 1 個から。

---

## 4. ホスト側＝ラズパイ本体 のセットアップ（構成A）

ノートPCの代わりにラズパイ本体を「常設ロガー」にする。室外/脱衣所に置き、USB で Pico と繋ぐ。

### 4.1 OS とポート確認

```bash
# ラズパイ本体(Raspberry Pi OS)で
sudo apt update && sudo apt install -y python3-pip git
# Pico を USB 接続すると通常 /dev/ttyACM0 として見える
ls /dev/ttyACM*        # → /dev/ttyACM0 があればOK
# シリアル権限(初回のみ)。再ログインで反映
sudo usermod -a -G dialout $USER
```

### 4.2 リポジトリと依存

```bash
git clone <repo> SAUNACFD && cd SAUNACFD
pip install -e .            # saunaflow CLI が入る
pip install pyserial        # ロガーに必須(daq log が内部で使用)
```

### 4.3 記録 → 変換 → メタ（既存 CLI）

```bash
# 1) 記録：30分(=1800s)を /dev/ttyACM0 から取得
saunaflow daq log --port /dev/ttyACM0 --duration 1800 \
    -o experiments/raw/session_001_raw.csv

# 2) 変換：生CSV → 検証用CSV(℃→K, status=ok/warn のみ, 定常検出)
saunaflow daq process experiments/raw/session_001_raw.csv --probe lower_bench

# 3) メタ：セッション条件を YAML 化
saunaflow daq meta experiments/raw/session_001_raw.csv \
    --session-id 001 --sensor-id DHT22-001 --probe lower_bench --probe-y 0.8
```

> ヘッドレス運用: SSH で入って `tmux`/`nohup` 配下で `daq log` を回せば、PC を繋ぎっぱなしにしなくてよい。電源が切れない場所に置く（計測中に落ちると 30 分が無になる）。

---

## 5. ベンチ・ブリングアップ手順（配線できてない→踏み込む、の最短ルート）

**いきなりサウナに入れない。** 机上で 1 段ずつ確認する。各段で OK が出てから次へ。

| # | 段階 | やること | OK 判定 |
|---|------|---------|---------|
| 1 | 目視 | 配線表(§3)どおりに繋ぐ。極性(VCC/GND)を二度見 | 逆挿し・浮きが無い |
| 2 | 導通 | テスターで VCC↔3V3, GND↔GND の導通、VCC↔GND が**ショートしていない**ことを確認 | ショート無し |
| 3 | 給電のみ | Pico を USB 接続(まだ firmware 無しでも可)。発熱・異臭が無いか | 異常発熱なし |
| 4 | firmware 書込 | Thonny 等で MicroPython を焼き、`firmware/` 一式を Pico ルートにコピー | 再起動で `main.py` 自動実行 |
| 5 | 単体確認 | Thonny シェル/シリアルモニタで JSON 行が**2秒ごと**に流れるか目視 | §2 の形の行が出る |
| 6 | センサ妥当性 | 手で握る/息を吹く → `temp_c`/`rh_pct` が動く。`-999.0` でないこと | 値が物理的に妥当 |
| 7 | 箱内温度 | DS18B20 が室温近傍を返し、`status` が `ok` | `box_temp_c`≈室温 |
| 8 | ロガー結合 | `saunaflow daq log --port ... --duration 60` を実行 | raw CSV に 約30行 |
| 9 | 変換 | `saunaflow daq process ...` | 検証用 CSV が出る |
| 10 | 延長試験 | 信号線を 1m→2-3m と延ばし、読みが安定するか | 欠損(-999)が5%未満 |

詰まりやすい所は §8。ここまで通れば measurement_implementation_plan.md の当日プロトコルに進める。

---

## 6. 高温点(upper_bench >80℃)の追加配線（Phase 2・K型熱電対）

DHT22/SHT も基板全体の連続耐熱は 100℃近傍で怪しい。upper_bench は **K型熱電対 + MAX31855(SPI)** で測る。

```text
  K型熱電対 ── MAX31855 基板 ── Pico WH (SPI)
                  VIN ──► 3V3(OUT) [物理36]
                  GND ──► GND      [物理38]
                  SCK ──► GP18 (SPI0 SCK) [物理24]  ※config化して使用
                  SO  ──► GP16 (SPI0 RX)  [物理21]
                  CS  ──► GP17            [物理22]
```

- ドライバ(`firmware/sensors/max31855.py`)は未実装。配線後に追加が必要（別タスク）。
- 多点・最短なら秋月 4ch K型キット(USIO-TEMP4CH, RP2040搭載・USB CSV 出力)で Pico を置き換える手もある（procurement §Phase2）。

---

## 7. 構成B：ラズパイ本体に直結（Pico なし・GPIO 直読み）

Pico を介さず、ラズパイ本体の GPIO に直接センサーを挿す。配線は減るが **Pi 側に小さなリーダ実装**が要る（既存 firmware は使えない）。

### 7.1 ラズパイ本体 GPIO 配線

```text
  SHT45 (I2C)              Raspberry Pi 40pin
   VIN ──► 3V3   [1番ピン]
   GND ──► GND   [6番ピン]
   SDA ──► GPIO2/SDA1 [3番ピン]
   SCL ──► GPIO3/SCL1 [5番ピン]

  DS18B20 (1-Wire, 箱内)
   VDD ──► 3V3   [1番ピン]
   DATA ─► GPIO4 [7番ピン]  (+ DATA–VDD 間 4.7kΩ)
   GND ──► GND   [9番ピン]
```

有効化:
```bash
sudo raspi-config        # Interface Options → I2C 有効, 1-Wire 有効
# /boot/config.txt に dtoverlay=w1-gpio が入る(1-Wire)
i2cdetect -y 1           # SHT45 が 0x44 に見えればOK
ls /sys/bus/w1/devices/  # 28-xxxx が DS18B20
```

### 7.2 必要な実装（未着手・別タスク）

構成Bでは Pico の代わりに **Pi 上の Python リーダ**が §2 の JSON 契約と同じ raw CSV を吐けばよい。最小案:
- `scripts/pi_direct_logger.py`(新規): `adafruit-circuitpython-sht4x` で SHT45 を、`/sys/bus/w1/...` で DS18B20 を読み、`src/daq/serial_logger.py` の `RAW_CSV_FIELDS` と同じ列(`time_s,temp_c,rh_pct,box_temp_c,status`)で `experiments/raw/*.csv` に直接書く。
- これにより `daq process` / `validation` / `reporting` は**無変更で再利用**できる。

> 構成Bは「机が無い・常設したい・配線を最小化したい」場合に向く。一方、Pico(構成A)は MicroPython が DHT22/DS18B20 ドライバ込みで**今すぐ動く**利点がある。**まずは構成A で 1 点取り切る**ことを推奨。

---

## 8. よくある失敗と対策

| 症状 | 原因 | 対策 |
|------|------|------|
| シリアルに何も来ない | USB が**充電専用ケーブル** | データ通信対応ケーブルに交換(§procurement) |
| `/dev/ttyACM0` が無い | ドライバ/接続 | `dmesg | tail` で認識確認、別ポート/ケーブル |
| Permission denied (port) | dialout 未所属 | `sudo usermod -a -G dialout $USER` → 再ログイン |
| `temp_c=-999` 連発 | プルアップ忘れ/配線逆/延長長すぎ | 4.7kΩ確認、極性確認、延長を1mに戻す |
| 値がふらつく/欠損多い | I2C/1-Wire の長距離 | 延長短縮、シールド線、サンプル間隔を空ける |
| `box_temp` が -999 | DS18B20 未検出 | 4.7kΩ、GP14/GPIO4 結線、`scan()`/`w1` 確認 |
| 箱内 `status=shutdown` | 箱が熱い | 保冷剤(袋+タオルで隔離)、箱をドア外/床へ |
| 結露でリセット | 保冷剤が電子部品に直付け | 保冷剤を離す・密閉しすぎない(結露逃げ) |

---

## 9. 着手チェックリスト

- [ ] センサー種別の確定（DHT22 / SHT45）→ §3 で対応する配線を選ぶ
- [ ] ホストの確定（ラズパイ本体 / PC）→ §4
- [ ] §3 の配線表どおり結線（プルアップ・極性）
- [ ] §5 ブリングアップ 1→10 を順に通す
- [ ] ベンチで `daq log`→`process` まで CSV が出ることを確認
- [ ] 断熱ボックス・保冷剤・固定具を用意（procurement §固定具）
- [ ] measurement_implementation_plan.md の当日プロトコルへ

---

## 10. 残タスク（このガイトの範囲外＝別途実装が必要）

| 項目 | 状態 | 備考 |
|------|------|------|
| DHT22 + DS18B20 + Pico (構成A) | ✅ firmware 実装済み・即動作 | 本ガイドの主経路 |
| SHT45 ドライバ (`firmware/sensors/sht45.py`) | ❌ 未実装 | I2C 0x44 / cmd 0xFD / CRC8。配線は §3.3 |
| K型熱電対 MAX31855 ドライバ | ❌ 未実装 | upper_bench 用。配線は §6 |
| ラズパイ直結リーダ (`scripts/pi_direct_logger.py`) | ❌ 未実装 | 構成B。§7.2 の契約に合わせる |
| 定常判定の自動 CLI | △ ロジックあり | `daq process` 内で `detect_steady_state` |

必要になった項目から個別タスクとして着手する。配線そのものは本ガイドで完結している。
