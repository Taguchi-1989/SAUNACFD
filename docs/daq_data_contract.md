# DAQデータ契約と将来想定形

## 1. 目的

計測機器が DHT22 から SHT45、K型熱電対、風速計へ増えても、ハーネス側の
入力形式を変えずに比較・再処理できることを目的とする。生データは事実として保存し、
校正、プローブ対応、イベント、処理条件は版管理されたメタデータへ分離する。

## 2. データの責務

```text
firmware JSONL
  -> raw CSV（追記専用・未補正）
    + session_meta.yaml（配置・校正・イベント・処理条件）
      -> processed CSV（CFDプローブ名、Kelvin、時刻整列済み）
        -> validation/reporting
```

- raw CSV は再現性の根拠なので、補正値を上書きしない。
- `session_meta.yaml` は `schema_version` を必須とし、Gitで管理する。
- processed CSV は派生物であり、raw CSV と metadata から再生成できる。
- センサーID、プローブ名、CFDケースIDを混同しない。

## 3. raw CSV v1

1行を「1時刻・1センサー」の観測とする縦持ち形式を採用する。

| 列 | 必須 | 単位 | 説明 |
|---|---:|---|---|
| `time_s` | yes | s | セッション開始からの単調増加時刻 |
| `sensor_id` | yes | - | metadata の `sensors[].id` と一致 |
| `temp_c` | 条件付き | degC | 温度を測るセンサーで必須 |
| `rh_pct` | 条件付き | %RH | 湿度を測るセンサーで必須 |
| `air_velocity_m_s` | 条件付き | m/s | 風速計で必須 |
| `box_temp_c` | no | degC | ロガー筐体の安全監視値 |
| `status` | yes | - | `ok`, `warn`, `shutdown`, `sensor_error` |

同一サンプリング周期に取得した観測は同じ `time_s` を使う。欠測は架空の値で埋めず、
行を欠落させるか空欄とし、`status` で理由を残す。旧単点CSVの空 `sensor_id` は
移行期間のみ受理する。

## 4. session_meta v1

正式スキーマは `configs/schemas/session_meta_schema.json` とする。

```yaml
schema_version: "1.0"
session:
  id: "20260714-001"
  started_at: "2026-07-14T14:00:00+09:00"
  timezone: "Asia/Tokyo"
  sampling_interval_s: 2
  case_id: "parametric_L1_13kW_transient"
environment:
  atmospheric_pressure_pa: 100800
  outdoor_temp_c: 31.2
  outdoor_rh_pct: 68
sensors:
  - id: "SHT45-LOWER"
    type: "SHT45"
    measures: [temperature, relative_humidity]
    position: {name: lower_bench, x_m: 1.5, y_m: 0.8, z_m: 1.25}
    calibration:
      temperature_offset_c: 0.1
      relative_humidity_offset_pct: -0.8
  - id: "TC-UPPER"
    type: "K_TYPE_MAX31855"
    measures: [temperature]
    position: {name: upper_bench, x_m: 1.5, y_m: 2.0, z_m: 1.25}
events:
  - {time_s: 900, type: loyly, water_mass_kg: 0.3}
  - {time_s: 930, type: aufguss_start}
  - {time_s: 990, type: aufguss_end}
processing:
  steady_state_window_s: 60
  steady_state_threshold_c_per_min: 0.1
  missing_value_policy: preserve
```

## 5. 想定する拡張段階

| 段階 | センサー | 主な検証対象 | 必要な出力 |
|---|---|---|---|
| Phase 1 | SHT45 x1-2 | K-01, K-07 | 定常温度、上下差 |
| Phase 2 | K型熱電対 + SHT85 | K-02, K-03, K-04 | ロウリュイベント、温湿度ピーク |
| Phase 3 | 熱線/ベーン風速計 | K-05, K-06 | アウフグース区間、風速時系列 |
| Phase 4-5 | 上記の複数セッション | 再現性、CFD比較 | case_id、校正履歴、自動レポート |

新しい測定量は raw CSV の列と `measures` enum を同じ変更単位で追加する。
ベンダー固有情報はトップレベルへ増やさず `extensions` に名前空間付きで格納する。

## 6. 互換性と移行

- 現行の `session_id` / `probe_position` 形式は legacy として読み込みを継続する。
- `saunaflow-daq meta` を含む新規セッションは v1 形式を使う。
- schema の必須項目や意味を変える場合は `1.x` を上書きせず `2.0` を追加する。
- processor は未知のメジャーバージョンを拒否し、黙って推測しない。
- raw と metadata の sensor ID 不一致、重複ID、重複プローブ名は処理エラーとする。

## 7. 実装境界

現在の processor は温度をKelvinへ変換し、複数センサーをプローブ列へ展開する。
湿度の絶対湿度変換、イベント基準の時刻ゼロ合わせ、再サンプリング、欠測補間は
この契約に入力を予約しているが、測定機器と検証要件が確定した段階で実装する。
