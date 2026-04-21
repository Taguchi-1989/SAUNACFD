# パラメトリックスタディ: Volume Source 出力と換気制御

**作成日**: 2026-04-21  
**計算条件共通**: buoyantSimpleFoam, M0 mesh (9,600 cells), viewFactor radiation, 50,000 iterations

---

## 1. 目的

前回セッション (Case J, 13kW volume source + pressureInletOutletVelocity 換気) で upper_bench 67°C (実測 80-100°C) を得た。
本セッションでは以下の2軸でパラメトリックスタディを実施:

1. **Volume source 出力**: 13kW → 6kW / 8kW (石の蓄熱・放射分を差し引いた有効対流伝熱)
2. **換気面積制御**: YAML area パラメータを実パッチ面積に変換する fixedValue BC の実装

---

## 2. 実装変更

### 2.1 換気速度スケーリング (case_builder.py)

YAML の `ventilation.supply.area` / `ventilation.exhaust.area` を「実効開口面積」として扱い、
メッシュパッチの実面積との比率で BC 速度をスケーリングする機能を追加。

```
v_BC = v_ref × (A_yaml / A_patch)
```

- `v_ref = 1.0 m/s` (開口部通過の基準風速)
- `A_patch`: blockMesh セグメントから自動計算した実パッチ面積
- `supply_patch_area`, `exhaust_patch_area` を context に追加

### 2.2 U.j2 テンプレート変更

supply_vent と exhaust_vent の両方に fixedValue BC オプションを追加:
- `supply_velocity > 0` の場合: `fixedValue` で流入速度を直接指定
- `exhaust_velocity > 0` の場合: `fixedValue` で流出速度を直接指定
- それ以外: 従来の `pressureInletOutletVelocity` にフォールバック

### 2.3 実パッチ面積

M0 メッシュでのセグメント分割により:
- Supply vent (x=0 壁, 最下部): **0.095 m²** (0.1m × 0.95m)
- Exhaust vent (opposite 壁, 最上部): **1.805 m²** (1.9m × 0.95m)

YAML area との乖離が大きく、pressureInletOutletVelocity では実際の ACH が制御不能だった。

---

## 3. ケース一覧

### J シリーズ (supply のみ fixedValue)

| Case | vol source | supply area | supply vel | exhaust BC |
|------|-----------|-------------|-----------|-----------|
| J-1 | 6kW | 0.010 m² | 0.105 m/s | pressureIO |
| J-2 | 8kW | 0.010 m² | 0.105 m/s | pressureIO |
| J-3 | 6kW | 0.005 m² | 0.053 m/s | pressureIO |
| J-4 | 8kW | 0.005 m² | 0.053 m/s | pressureIO |

### K シリーズ (両側 fixedValue)

| Case | vol source | supply vel | exhaust vel |
|------|-----------|-----------|-------------|
| K-1 | 13kW | 0.105 m/s | 0.0083 m/s |
| K-2 | 13kW | 0.053 m/s | 0.0044 m/s |
| K-3 | 8kW | 0.053 m/s | 0.0044 m/s |

---

## 4. 結果

### 4.1 J シリーズ (50k iter)

| Case | upper (°C) | lower (°C) | floor (°C) | vol-avg (°C) |
|------|-----------|-----------|-----------|-------------|
| J-1 (6kW, std) | 46.4 | 29.0 | 23.3 | 35.7 |
| J-2 (8kW, std) | 52.8 | 30.4 | 23.8 | 39.1 |
| J-3 (6kW, half) | 46.3 | 29.1 | 23.4 | 35.8 |
| J-4 (8kW, half) | 53.0 | 30.5 | 23.9 | 39.2 |
| **実測目標** | **80-100** | **40-60** | **25-35** | — |

### 4.2 K シリーズ (50k iter)

| Case | upper (°C) | lower (°C) | floor (°C) | vol-avg (°C) |
|------|-----------|-----------|-----------|-------------|
| K-1 (13kW, std) | 67.4 | 32.9 | 25.3 | 47.1 |
| K-2 (13kW, half) | 64.8 | 32.5 | 25.3 | 46.2 |
| K-3 (8kW, half) | 54.7 | 31.8 | 25.2 | 40.6 |
| Case J (参考) | 67 | 29 | 23 | 44 |
| **実測目標** | **80-100** | **40-60** | **25-35** | — |

---

## 5. 分析と知見

### 5.1 換気面積変更の効果は無視可能

- J-1 ≈ J-3 (46.4 vs 46.3°C)、J-2 ≈ J-4 (52.8 vs 53.0°C)
- K-1 ≈ K-2 (67.4 vs 64.8°C)
- **supply 側のみ fixedValue にしても、exhaust の pressureIO が浮力駆動で自由に流出するため、換気量は制御できない** (J シリーズ)
- **両側 fixedValue にしても換気面積半減で 2.6°C しか変わらない** (K シリーズ)

**結論**: 換気は温度場の支配因子ではない。

### 5.2 Volume source 出力が温度場を支配

- 6kW → 8kW → 13kW で upper = 46 → 53 → 67°C
- ほぼ線形 (ΔT ≈ 3°C/kW)
- 目標 90°C には ~21kW 必要 → 全ヒーター出力 18kW を超過

### 5.3 Steady state 未到達

- K-1 壁面損失推定: 1.5 × 37.5 × 47 ≈ 2,644W (13kW 入力の 20%)
- 残り 80% が蓄熱中 → 50k iter では steady state に到達していない
- iter 延長 (100k+) で温度はさらに上昇するはず

### 5.4 以前の「換気が支配的」仮説の検証

前回セッションで Case J (pressureIO) の upper 67°C に対し換気なしの Case I が 235°C だったため、「換気が支配的」と結論した。しかし:

- Case I は wall_htc=1.5 (断熱的) で壁面損失が小さく、volume source 13kW がほぼ全て空気加熱に使われた
- Case J の pressureIO vent は巨大パッチ (1.8 m²) で大量排気 → 温度大幅低下
- K シリーズで fixedValue にして flow rate を制限すると、**壁面損失が主要冷却パスであることが判明**
- つまり Case J の低温は「過大な換気パッチ面積」の artifact だった

---

## 6. 残課題

### 6.1 Steady state 収束

50k iter で蓄熱率 ~80% → 最低でも 100k-200k iter が必要。
buoyantPimpleFoam transient で物理時間を直接追跡する方が効率的な可能性あり。

### 6.2 Volume source の物理的妥当性

13kW を空気に直接注入するモデルは非現実的 (steady 235°C)。
実ヒーターは石を加熱 → 石表面から対流+放射 → 有効対流 5-8kW。
ただし 8kW でも目標の半分程度の温度にしか到達しない (55°C)。
Steady state 到達後の温度を見てから volume source 出力を再評価すべき。

### 6.3 メッシュの換気パッチ面積

YAML area とメッシュ面積の乖離 (0.01 vs 0.095 m²) は構造的問題。
blockMeshDict のセグメント分割を改善して実サイズの小さな換気パッチを作るか、
M1 メッシュで解像度を上げてパッチサイズを縮小する必要がある。

---

## 7. ファイル一覧

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/harness/case_builder.py` | supply/exhaust パッチ面積計算、速度スケーリング context 追加 |
| `foam_templates/base_case/0/U.j2` | supply/exhaust fixedValue BC 条件分岐追加 |

### 新規ケース定義

| ファイル | 説明 |
|---------|------|
| `configs/cases/parametric_J1_6kW_vent_std.yaml` | J-1: 6kW + std vent |
| `configs/cases/parametric_J2_8kW_vent_std.yaml` | J-2: 8kW + std vent |
| `configs/cases/parametric_J3_6kW_vent_half.yaml` | J-3: 6kW + half vent |
| `configs/cases/parametric_J4_8kW_vent_half.yaml` | J-4: 8kW + half vent |
| `configs/cases/parametric_K1_13kW_vent_controlled.yaml` | K-1: 13kW + both fixedValue std |
| `configs/cases/parametric_K2_13kW_vent_half.yaml` | K-2: 13kW + both fixedValue half |
| `configs/cases/parametric_K3_8kW_vent_half.yaml` | K-3: 8kW + both fixedValue half |

### 実行スクリプト

| ファイル | 説明 |
|---------|------|
| `scripts/build_parametric_J.py` | J シリーズ 4ケースビルド |
| `scripts/run_parametric_J.sh` | J シリーズ全実行 |
| `scripts/run_parametric_J12.sh` | J-1/J-2 実行 |
| `scripts/run_parametric_J_all.sh` | J 全ケース (fixedValue supply) |
| `scripts/run_parametric_K.sh` | K シリーズ全実行 |

---

## 8. 結論

| 知見 | 詳細 |
|------|------|
| 換気は支配因子ではない | 面積半減で <3°C の変化 |
| Volume source 出力が温度を決定 | 3°C/kW の線形応答 |
| Steady state 未到達 | 50k iter で蓄熱 80%、100k+ 必要 |
| pressureIO の巨大パッチ | Case J の低温は過大排気の artifact |
| fixedValue 両側制御が有効 | 換気量の定量的制御が可能に |

**次ステップ**: K-1 を 100k iter に延長し steady state 到達度を確認。
その後 volume source 出力を再評価。

---

**計算時間**: 各ケース約 8-25 分 (50k iter, M0 mesh, WSL2)  
**全テスト**: 255+ passing
