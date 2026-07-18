# OpenFOAM buoyantPimpleFoam トラブルシューティング記録

本ドキュメントは SaunaFlow の OpenFOAM ケースを初回実行する際に遭遇した
エラーと修正を時系列で記録したものである。
今後の OpenFOAM テンプレート開発やハーネス改修時の参考とする。

## 環境

- OpenFOAM 2312 (openfoam.com)
- WSL2 Ubuntu on Windows 11
- ソルバー: buoyantPimpleFoam (非定常圧縮性浮力駆動流)
- 乱流モデル: SST k-omega
- メッシュ: M0 (9600 cells, 9-block structured hex)

## エラーと修正の時系列

### 1. `wallDist/method` not found

**エラー:**
```
Entry 'method' not found in dictionary "system/fvSchemes/wallDist"
```

**原因:** SST k-omega は壁面距離場を必要とするが、fvSchemes に `wallDist` セクションがなかった。

**修正:** `fvSchemes.j2` に追加:
```
wallDist
{
    method  meshWave;
}
```

**教訓:** SST k-omega (または任意の壁面距離依存モデル) を使う場合は必須。

---

### 2. `fvOptions/buoyancyProduction` に `name` エントリなし

**エラー:**
```
Entry 'name' not found in dictionary "constant/fvOptions/buoyancyProduction"
```

**原因:** OpenFOAM 2312 の `scalarCodedSource` はトップレベルに `name` キーが必要。
`scalarCodedSourceCoeffs` 内の `name` だけでは不十分。

**修正:** `fvOptions.j2` のトップレベルに `name buoyancyProductionK;` を追加。

**教訓:** codedSource のエントリ名と `name` キーは別物。バージョン依存あり。

---

### 3. `div(((rho*nuEff)*dev2(T(grad(U)))))` not found

**エラー:**
```
Entry 'div(((rho*nuEff)*dev2(T(grad(U)))))' not found in divSchemes
```

**原因:** 圧縮性ソルバー (buoyantPimpleFoam) は粘性応力テンソルに密度を含む形式を使う。
非圧縮性用の `div((nuEff*dev2(T(grad(U)))))` だけでは不足。

**修正:** `fvSchemes.j2` に両方追加:
```
div((nuEff*dev2(T(grad(U)))))         Gauss linear;
div(((rho*nuEff)*dev2(T(grad(U)))))   Gauss linear;
```

**教訓:** 圧縮性/非圧縮性で div スキームの変数名が異なる。

---

### 4. `div(phi,h)` not found

**エラー:**
```
Entry 'div(phi,h)' not found in divSchemes
```

**原因:** `sensibleEnthalpy` エネルギー形式では温度 T ではなくエンタルピー h を輸送する。
`div(phi,T)` はあったが `div(phi,h)` がなかった。

**修正:** `fvSchemes.j2` に追加:
```
div(phi,h)  bounded Gauss linearUpwind default;
```

`fvSolution.j2` のソルバー正規表現にも `h` を追加:
```
"(U|T|h|k|omega|epsilon)"
```

**教訓:** `energy sensibleEnthalpy` → `h` を解く。`energy sensibleInternalEnergy` → `e` を解く。

---

### 5. FPE (Floating Point Exception) — ゼロ除算

**エラー:**
```
sigFpe::sigHandler(int) → divide → operator/
```

**原因:** G_b の codedSource で `Gb / (k + 1e-15)` の除算、または
ソルバー内部の `1/(R*T)` 計算でゼロ除算。

**修正:**
1. G_b を explicit source に変更 (`eqn += Gb` — `SuSp` を使わない)
2. `rho` の min ガード (`max(rho, 0.5)`)
3. `FOAM_SIGFPE=false` で FPE trap を無効化

**教訓:** codedSource での除算は要注意。初期状態で k=0 のセルがある場合に危険。

---

### 6. `fvSolution` に `rho` ソルバーなし

**エラー:**
```
Entry 'rho' not found in dictionary "system/fvSolution/solvers"
```

**原因:** buoyantPimpleFoam は密度場も解くが、fvSolution にソルバー設定がなかった。

**修正:** `fvSolution.j2` に追加:
```
rho     { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0.1; }
rhoFinal { $rho; relTol 0; }
```

**教訓:** 圧縮性ソルバーは rho を明示的に解く。

---

### 7. p_rgh 初期値 = 0 による NaN

**エラー:**
```
GAMG: Solving for p_rgh, Initial residual = nan
```

**原因:** `p_rgh` の初期値が 0 Pa、`p` が 101325 Pa、`pRefValue` が 0。
密閉キャビティで全壁面 `fixedFluxPressure` の場合、圧力参照が不整合になり
`p ≈ 0` → `rho = p/(R*T) ≈ 0` → NaN。

**修正:**
1. `p_rgh` 初期値を 101325 Pa に変更
2. `pRefValue` を 101325 に設定
3. `hRef` ファイルを追加 (value = 0)

**教訓:** 密閉キャビティでは `p_rgh` の初期値と `pRefValue` を大気圧に揃える。
`hRef = 0` は `g.h` の参照高さ。

---

### 8. externalWallHeatFluxTemperature による発散

**エラー:** 上記 #7 と同じ NaN だが、p_rgh 修正後も発生。

**原因:** `externalWallHeatFluxTemperature` + `kappaMethod fluidThermo` が
初期の均一温度場で `kappa` を正しく計算できず、
最初のタイムステップで h が発散 → T が不正値 → rho が 0。

**修正:** ヒーター壁面を `fixedValue` (固定温度) に変更。
温度は `T_heater = T_wall + q / h_eff` で推定 (h_eff = 200 W/(m²K), 上限 +300K)。

**教訓:** 高熱流束の `externalWallHeatFluxTemperature` は初期状態との整合が難しい。
`fixedValue` で始めて、安定後に熱流束 BC に切り替えるのが安全。

---

### 9. deltaT が大きすぎて発散

**原因:** 初期 deltaT=0.05s で高熱流束 → h が 1 ステップで発散。

**修正:** `controlDict.j2` の初期 deltaT を 0.001s に設定。
`maxCo = 0.3`, `maxDeltaT = 0.5` で adaptive stepping が徐々にランプアップ。

**教訓:** 圧縮性浮力駆動流は初期ステップが最も不安定。
`deltaT = 0.001` 以下から始め、Courant 数制御で自動調整させる。

---

### 10. codedSource が `Not implemented` で abort（2026-07 判明）

**エラー:**
```
--> FOAM FATAL ERROR: Not implemented
    From virtual void Foam::fv::...::addSup(const Foam::volScalarField&, Foam::fvMatrix<double>&, Foam::label)
```

**原因:** 圧縮性ソルバー (buoyant*Foam) の fvOptions は rho 付きの
`addSup(rho, eqn, fieldi)` を呼ぶが、codedSource に `codeAddSup` しか
定義していなかった。rho 変種は `codeAddSupRho` に書く必要がある。
つまり **buoyancyProduction / aufgussJet の codedSource は今まで一度も
実行されていなかった**（従来は手前の発散か wmake 不在で到達不能だった）。

**修正:** `fvOptions.j2` の codedSource に `codeAddSupRho` を追加。
rho は引数で渡ってくるので lookupObject は不要（再宣言するとコンパイルエラー）。

**教訓:** 圧縮性ソルバー + codedSource は `codeAddSupRho` が本体。

---

### 11. WSL に wmake が無く codedSource がコンパイル不能（2026-07 判明）

**エラー:**
```
--> FOAM FATAL ERROR: exec(wmake, ...) failed
```

**原因:** `openfoam2312` (runtime) パッケージのみインストールされており、
wmake / ヘッダを含む開発パッケージが無かった。

**修正:** `sudo apt install openfoam2312-dev`（インストール済み 2026-07-18）。

---

### 12. surface_flux ヒーター (externalWallHeatFluxTemperature mode flux) は初回ステップから発振（2026-07 判明）

**エラー:** FPE (`Foam::divide`)。PIMPLE 外部反復で h / p_rgh の残差が
反復ごとに ~×30 成長し、最終反復で圧力系が崩壊。

**原因:** 立ち上がりは壁近傍が層流 (alphat≈0) のため κ_eff = κ_laminar。
q=60000 W/m² を半セル (0.0625 m) の伝導で受けると境界面温度が
T_face = T_cell + q·δ/κ ≈ 1.4e5 K となり、面の rho/h が非物理的な値になって
圧力-エネルギー結合が初回タイムステップ内で発振する。
初期場（2-Zone/一様）・codedSource・ddt スキーム・bounded div は無関係
（各々単独に切って再現することを確認済み）。

**修正:** ベースラインは `heater.model: volume_source`（topoSet の
heaterZone + scalarSemiImplicitSource）に変更。壁面特異性が無く、
FOAM_SIGFPE=true（トラップ有効）のまま 300 秒完走を確認。
surface_flux を使う場合は q の時間ランプ（table）+ 発達した乱流場からの
リスタートが必要。

**検証結果 (dry_sauna_steady, M0, 18kW, FOAM_SIGFPE=true):**
- 300 秒完走、FPE ゼロ、Courant max ≈ 0.30 (=maxCo)
- 温度成層再現: 上段 464 K > 下段 413 K > 床 334 K

---

## チェックリスト: buoyantPimpleFoam ケース作成時

- [ ] `fvSchemes`: `wallDist { method meshWave; }` を含む
- [ ] `fvSchemes`: `div(phi,h)` と `div(((rho*nuEff)*dev2(...)))` を含む
- [ ] `fvSolution`: `rho` / `rhoFinal` ソルバーを含む
- [ ] `fvSolution`: `pRefValue` が `p_rgh` 初期値と一致
- [ ] `p_rgh`: 初期値 = 大気圧 (101325 Pa)
- [ ] `constant/hRef`: 存在する (value = 0)
- [ ] `controlDict`: `deltaT` が十分小さい (0.001 推奨)
- [ ] `controlDict`: `maxCo ≤ 0.5`, `adjustTimeStep yes`
- [ ] `codedSource`: 圧縮性ソルバーでは `codeAddSupRho` に本体を書く（#10）
- [ ] ヒーター: `model: volume_source` が安定（surface_flux は発振する — #12）
- [ ] PIMPLE: 中間外部反復に relaxationFactors（h 0.5, U/k/omega 0.7, Final 1）
- [ ] FOAM_SIGFPE は既定でトラップ有効のまま実行できる（#12 修正後）。
      発散調査時のみ `FOAM_SIGFPE=false` で延命させる
