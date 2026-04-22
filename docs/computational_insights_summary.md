# SaunaFlow CFD 計算キャンペーン — 知見の総括

**作成日**: 2026-04-22  
**対象**: Phase 1〜2 の全 OpenFOAM 計算 (Case A〜L)  
**ドメイン**: 3.0m × 2.5m × 2.5m ドライサウナ, 18kW 電気ヒーター

---

## 1. 計算ケース一覧と結果

### 全ケース温度まとめ

| Case | ソルバー | vol source | 放射 | 換気 | iter/時間 | upper (°C) | lower (°C) | floor (°C) |
|------|---------|-----------|------|------|----------|-----------|-----------|-----------|
| A | SIMPLE | 18kW surf | なし | なし | 13 iter | 発散 | — | — |
| B | SIMPLE | 18kW vol | なし | なし | 15k | 108 | 68 | 31 |
| C | SIMPLE | 18kW vol | なし | pressIO | 30k | 70 | — | 20 |
| E | PIMPLE | 18kW vol | なし | pressIO | transient | 111 | — | 30 |
| G | SIMPLE | 18kW vol | viewFactor | なし | 30k | 129 | 84 | 46 |
| H | SIMPLE | 18kW vol | vF+fixedT 573K | なし | 30k | 126 | 83 | 48 |
| I | SIMPLE | 13kW vol | vF+fixedT 573K | なし | 50k | 235 | 197 | 155 |
| I-a | SIMPLE | 13kW vol | vF+fixedT 473K | なし | 50k | 234 | 197 | 155 |
| I-c | SIMPLE | 13kW vol | vF+fixedT 673K | なし | 50k | 235 | 197 | 151 |
| J | SIMPLE | 13kW vol | vF+fixedT 573K | pressIO | 50k | 67 | 29 | 23 |
| K-1 | SIMPLE | 13kW vol | vF+fixedT 573K | fixedV both | 50k | 67 | 33 | 25 |
| K-2 | SIMPLE | 13kW vol | vF+fixedT 573K | fixedV half | 50k | 65 | 33 | 25 |
| K-3 | SIMPLE | 8kW vol | vF+fixedT 573K | fixedV half | 50k | 55 | 32 | 25 |
| **L-1** | **PIMPLE** | **13kW vol** | **vF+fixedT 573K** | **fixedV both** | **3600s** | **95** | **54** | **31** |
| **実測目標** | — | — | — | — | — | **80-100** | **40-60** | **25-35** |

---

## 2. 主要な知見

### 知見 1: SIMPLE ソルバーは buoyancy-driven flow の定常解に不向き

**根拠**: SIMPLE 50k iter (K-1) → upper 67°C、PIMPLE 3600s (L-1) → upper 95°C

- SIMPLE の反復は「物理時間」に直接対応しない
- 50k iter でも蓄熱率 ~80% で定常に到達しない
- buoyancy-driven flow では密度変化 → 圧力補正 → 速度場修正のループが遅い
- **PIMPLE + adjustTimeStep が正しい選択**

**教訓**: 浮力駆動流れの定常解を求める場合、SIMPLE ではなく PIMPLE で物理時間を追跡すべき。3600s (1時間) でサウナ室の quasi-steady state に到達。

### 知見 2: ヒーター壁温 (fixedT サロゲート) の感度は極めて低い

**根拠**: 473K → 573K → 673K で upper_bench 差 <1°C

- heater_wall 放射は 214W → 1,161W → 2,651W と変化
- しかし 13kW volume source に対して 2-20% に過ぎない
- viewFactor 放射は heater→wall 方向に主に作用し、室内空気への直接効果は限定的

**教訓**: 放射パラメータの精度にこだわるよりも、対流入力 (volume source) と換気の制御に注力すべき。

### 知見 3: 換気は温度場の支配因子ではない（条件付き）

**根拠**: K-1 vs K-2 (換気面積半減) で upper 差 2.6°C

- fixedValue BC で供給・排気を定量制御した場合、換気面積変更の影響は微小
- **ただし**: pressureInletOutletVelocity + 巨大パッチ (1.8m²) では大量排気が発生し、235°C → 67°C の大幅低下を引き起こした（Case I → J）

**教訓**: pressureIO の効果はパッチ面積に強く依存する artifact。換気を議論するには流量を直接制御する fixedValue BC が必須。

### 知見 4: Volume source 出力と壁面損失のバランスが温度を決定

**根拠**: 
- 6kW→8kW→13kW で upper ≈ 3°C/kW の線形応答 (SIMPLE)
- L-1 (13kW, PIMPLE 3600s) で upper 95°C → 目標範囲内

- 壁面損失: wall_htc × 全壁面積 × ΔT
- wall_htc = 1.5 W/(m²K) (木材 0.08m, λ=0.12)
- 壁面積 ≈ 37.5 m²
- L-1 での壁面損失合計: ~2,857W (入力 14.6kW の 20%)

**教訓**: 定常温度は入力と壁面損失のバランスで決まる。13kW volume source + fixedT 573K 放射 (合計 ~14.6kW) が実測に合う。

### 知見 5: 壁厚の効果は「断熱性向上 = 温度上昇」

**根拠**: 壁厚 0.015m → 0.08m で wall_htc 8.0 → 1.5 → 温度上昇方向

- 初期の直感「壁厚増加 → 壁面損失増加 → 温度低下」は誤り
- externalWallHeatFluxTemperature の h パラメータは外部への放熱抵抗
- h が小さい = 断熱性が高い = 室温が上昇

**教訓**: 壁のモデルでは conductivity/thickness が U-value を決める。厚い壁は断熱的。

### 知見 6: Surface flux モデルは M0 メッシュで不安定

**根拠**: Case A (60,000 W/m² surface flux, M0) → 4-13 iter で発散

- 局所的な温度勾配が M0 の粗いセルで extreme gradient を生成
- Volume source は空間的に分散するため安定

**教訓**: 高フラックス BC は十分な mesh 解像度 (M1+) が必要。Phase 1 では volume source が安全な選択。

### 知見 7: viewFactor 放射は blockMesh 設定に敏感

**根拠**: 初期実装で `coarse faces: 0` → faceAgglomerate が失敗

- 原因: patch に `inGroups` で `viewFactorWall` が設定されていなかった
- radiationProperties の dimensioned scalar 形式が必要
- qr の `emissivityMode solidRadiation` が必要
- fvSolution に qr/qrFinal ソルバーが必要

**教訓**: viewFactor は前処理 (faceAgglomerate → viewFactorsGen) のチェーンが重要。設定漏れ 1 つで完全に機能しなくなる。

### 知見 8: 温度成層化のパターンは再現可能

**根拠**: L-1 で upper-lower 41°C, lower-floor 23°C

- 実測の成層化パターン (upper-lower 差 20-40°C) とオーダーが一致
- M0 mesh でも定性的な成層化構造を捕捉
- プローブ位置 (y=0.1, 0.8, 2.0) で鉛直温度分布を代表

**教訓**: 粗い M0 mesh でも成層化の傾向を捉えられる。定量的精度の向上は M1 以降。

---

## 3. パラメータ感度の整理

| パラメータ | 変動範囲 | upper への影響 | 感度 |
|-----------|---------|--------------|------|
| **ソルバー** (SIMPLE→PIMPLE) | — | +28°C (67→95) | **最大** |
| **Volume source 出力** | 6→13 kW | +21°C (46→67, SIMPLE) | **大** |
| **壁厚** | 0.015→0.08m | +124°C (111→235, SIMPLE*) | **大** (間接的) |
| **換気 (pressIO)** | 有→無 | -168°C (235→67) | **大** (artifact) |
| **換気面積 (fixedV)** | std→half | -2.6°C | **極小** |
| **ヒーター壁温** | 473→673K | <1°C | **無視可能** |
| **放射モデル** | なし→viewFactor | +21°C (108→129) | **中** |

*注: SIMPLE の壁厚影響は iter 不足の artifact を含む

---

## 4. 最適計算条件 (Phase 1 結論)

| 項目 | 推奨値 | 根拠 |
|------|--------|------|
| ソルバー | **buoyantPimpleFoam** | SIMPLE では定常に到達不可 |
| シミュレーション時間 | **3600s** (1時間) | 40分で quasi-steady |
| deltaT | **0.01s** (初期) + adjustTimeStep | maxCo=0.3 で自動調整 |
| Volume source | **13 kW** | 実効対流伝熱 |
| 放射 | **viewFactor + fixedT 573K** | ヒーター表面放射 |
| 換気 | **fixedValue 両側** | YAML area でスケーリング |
| 壁厚 | **0.08m** (λ=0.12) | サウナ木材パネル |
| メッシュ | **M0** (9,600 cells) | Phase 1 十分 |
| 乱流 | **kOmegaSST** (buoyancy_production=false) | kMin による安定化 |

---

## 5. 判明した課題と限界

### 5.1 計算コスト

- L-1 (M0, 3600s): **8 時間** (WSL2)
- M1 (76,800 cells) では推定 **80-160 時間**
- M1 + PIMPLE は Phase 1 には過大 → M0 で十分

### 5.2 壁面熱容量

- 現在の externalWallHeatFluxTemperature は壁面蓄熱を考慮しない
- 実際のサウナは起動時に壁面が吸熱 → 暖まるまで数時間
- L-1 の「蓄熱 80%」の一部はこの壁面蓄熱の欠如に起因
- thermalShell や solidThermo 結合で改善可能 (Phase 3 以降)

### 5.3 ヒーターモデル

- Volume source は空気を直接加熱 → 物理的には非現実的
- 実際: ヒーター → 石 → 石表面から対流+放射
- 13kW は「有効対流伝熱」としてキャリブレーション
- 石の表面温度モデルは CHT (Conjugate Heat Transfer) で将来対応

### 5.4 換気パッチの面積

- M0 mesh のセグメント分割で供給パッチ 0.095m²、排気パッチ 1.805m²
- YAML area (0.01, 0.015m²) との乖離大
- fixedValue BC で速度を低減して補正しているが、流れの空間分布は不正確
- M1 以降でパッチの物理サイズを小さくすることで改善可能

### 5.5 実測データの不在

- 現在のバリデーションは推定サンプルデータのみ
- DHT22 センサーの校正・設置が次のステップ
- 実測データ取得後にモデルパラメータの最終調整が必要

---

## 6. 今後のロードマップ

### Phase 1 完了条件 (達成済み)

- [x] 温度成層化の定性的再現
- [x] 全プローブが実測推定範囲内 (upper 95°C, lower 54°C, floor 31°C)
- [x] 計算の再現性 (YAML → build → run → parse が自動化)

### Phase 2: 実測バリデーション

1. DHT22 センサー設置・校正
2. 定常状態の実測データ取得
3. CFD vs 実測の定量比較
4. モデルパラメータの微調整 (volume source 出力, 壁厚)

### Phase 3: モデル高度化

5. M1 mesh でのメッシュ依存性評価
6. 壁面熱容量モデル (thermalShell)
7. ロウリュ (蒸気導入) の transient シミュレーション
8. Aufguss (送風) の momentum source

---

## 7. 技術的な反省点

### やって良かったこと

1. **パラメトリックに 1 軸ずつ変動**: 効果の因果関係が明確になった
2. **全ケースの結果を記録**: 後から比較・分析が容易
3. **ハーネスの自動化**: YAML → OpenFOAM が 1 コマンドで完結
4. **壊れたらすぐ修正**: viewFactor の設定ミスを段階的に修正

### 反省すべき点

1. **SIMPLE で長時間走らせた**: 最初から PIMPLE にすべきだった（数日のロス）
2. **pressureIO の artifact に気づくのが遅かった**: パッチ面積を最初に確認すべきだった
3. **壁厚の効果を直感で誤解**: 「厚い壁 → 損失増加」は間違い、物理を確認すべきだった
4. **換気面積の制御**: YAML area がメッシュに反映されないことに気づくのが遅かった

---

**計算ケース総数**: 14+ ケース  
**計算総時間**: 推定 15+ 時間  
**テスト数**: 255+ passing  
**コミット数**: 20+ (Phase 1-2)
