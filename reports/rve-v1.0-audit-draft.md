# RVE v1.0 仕様適合監査資料（Feel2提出用ドラフト）

作成日: 2026-10-24
対象リポジトリ: `watag/RVE-pjt`
公開監査ブランチ: `agent/rve-v1.0-audit`（`main`から分離）
対象base HEAD: `10e8ca6f578d7f99cd661f6c95dea237267053ce`
監査状態: Feel2未提出・未監査。本資料は仕様適合の宣言ではない。

## 1. 作業状態と保全

調査開始時の状態:

- tracked変更: `ops/a52-agent/README.md`, `ops/a52-agent/runner.py`, `ops/a52-agent/test_runner.py`（計113 insertions）
- untracked: `.agent-state/logs/e2e-005.codex.log`, `.agent-state/logs/runner.log`, `.agent-state/runner.lock`, `.agent-state/worktrees/test-codex/`、および `config/`, `fetch/`, `layer1/`, `reports/`, `requirements.txt`, `tests/` 内の作業ファイル
- `.agent-state/` とRunnerの内容は変更していない。既存差分の編集・削除・移動、commit、pushも行っていない。
- 当初の調査時は本資料だけを追加した。PR準備では独立worktreeに監査対象ファイルを選択コピーし、規範仕様と再現ガイドを新規作成した。元worktreeは変更していない。
- `data/raw/` と `data/processed/` には `.gitkeep` のみ。実価格系列は存在しない。
- 元の作業ツリーにはRVE規範文書がなかったため、確定ユーザー仕様を `docs/rve-v1.0-spec.md` として監査対象branchへ記録した。

Feel2の独立レビュー結果は含まない。GitHub PR上の公開により監査役が参照できる状態を用意するが、Feel2が当該リポジトリへアクセス可能か、および監査依頼を受領したかは未確認。

## 2. 実行した検証

実行環境: `/tmp/rve-layer1-ubuntu-venv` のPython 3.12。再現手順は `docs/rve-v1.0-audit-guide.md`。実行コマンド:

```text
PATH=/tmp/rve-layer1-ubuntu-venv/bin:$PATH PYTHONPYCACHEPREFIX=/tmp/rve-layer1-pycache python -m unittest discover -s tests -v
```

結果: 34 tests, `OK`。実行環境はPython 3.12.3 / NumPy 2.5.4 / pandas 3.0.6。requirements.txtのピン（NumPy 2.4.3 / pandas 3.0.1）をこのランで再インストールしていないため、宣言依存バージョンでの実行は未確認。テスト名と実測ログは `reports/rve-v1.0-test-log.txt`。内訳は fetch 5、旧Layer 1回帰 8、daily-to-vector 2、portfolio 6、risk metrics 8、weekly preparation 5。

`py_compile`対象のLayer 1/fetch/test Pythonファイルは成功。`git diff --check`は成功（出力なし）。合成fixtureを使ったrisk-vector数値照合も実行した。テストと数値は合成データのみで、実データ取得・品質確認を意味しない。

## 3. 仕様適合表

### 1. 価格データ取得・差分更新

- 要求: 設定された5アンカーと対象銘柄を取得し、2年固定上書きではなく履歴を維持する増分更新を行う。
- 根拠: `fetch/fetch_csv.py:9-14,59-100,103-148`; `config/tickers.yaml:1-23`。
- 実際: 初回は260週を要求する起点で取得し、既存履歴が十分なら最新日から7日重複して取得。新しい重複行を優先し全履歴を保持し、一時ファイルから置換する。設定はToyota + 5アンカー + JPY=Xの7銘柄。
- テスト: `test_first_fetch_backfills_five_year_warmup`, `test_short_existing_history_triggers_backfill`, `test_mature_history_updates_from_recent_overlap`, `test_merge_preserves_history_and_replaces_overlapping_dates`, `test_fetch_saves_delta_without_dropping_older_rows`。期待値/実測: 開始日が260週前または2026-10-20から7日前の2026-10-13、overlap close 150→151、保存行は2020-01-03を保持し重複0。全件pass。
- 判定: **一部適合／未確認**。ローカル増分・merge動作はpass。実Yahoo取得、各tickerの利用可能期間、取得失敗時のatomicityは未検証。`Close`のみ選択し、調整後価格の意味も未確認。
- 対応案: 実データの取得可否とプロバイダの`Close`/`Adj Close`定義を別途確認し、調整方針を明記する。現状データなし。

### 2. 週次リターン生成

- 要求: W-FRI、金曜休場時は週最終価格、実価格日を保持、単純リターン、欠損週を補完しない。
- 根拠: `layer1/weekly.py:33-45,55-73,75-113`。
- 実際: 日付を週末金曜へ割当て、週内最終行を採用し`price_date`を保持。週インデックスを明示生成し欠損週を残す。隣接する有効週価格のみで`P_t/P_(t-1)-1`を計算。
- テスト: `test_uses_last_observation_when_friday_is_a_market_holiday`（100→110、期待/実測10%）、`test_missing_week_is_explicit_and_does_not_bridge_returns`、`test_nonpositive_final_weekly_price_is_invalid_without_earlier_fallback`、`test_duplicate_daily_date_is_configuration_error`、`test_missing_close_on_final_observation_is_not_skipped`。全件pass。
- 判定: **ローカル仕様テスト適合／実データ未確認**。
- 対応案: 実際の複数市場カレンダーと時刻/タイムゾーンで週割当てを検証する。

### 3. 為替換算

- 要求: USD資産はJPY価格へ換算後にリターン計算。為替を第6β軸にしない。
- 根拠: `layer1/weekly.py:3-5,33-45`; `layer1/layer1_vector.py:12-23,38-55`; 旧mainのticker構成 `layer1/layer1_vector.py:107-114`。
- 実際: v1入口は入力価格が同一分析通貨に換算済みという前提だが、変換処理はない。旧mainはJPY=Xを独立factorとして含み、^GSPC/TLTのJPY換算も行わない。設定にもcurrency/source metadataなし。
- 対応テスト: USD×FX価格のテストなし。旧回帰テストは旧仕様固定で本要求を検証しない。
- 判定: **不適合**。
- 対応案: FX日時整列規則を確定後、価格変換モジュールと単体/統合テストを追加し、JPY=Xをベクトル軸から除外する。FX欠損statusも接続する。

### 4. β計算

- 要求: 週次単純リターン、各5アンカー独立単回帰、直近52週、切片ありOLSの傾きと同じ。
- 根拠: v1 `layer1/risk_metrics.py:79-98,149-200`; legacy `layer1/beta.py:20-54`。
- 実際: v1は標本共分散/標本分散を52週で計算し、アンカー別statusを返す。legacyは日次log return、既定120、anchorをffill/bfillし、sample covariance/population varianceを使用。
- テスト: `test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline `test_daily_prices_produce_specification_based_weekly_vector`, `test_zero_variance_anchor_has_its_own_status`, 欠損/アンカー設定テスト。合成fixtureの期待式と実測差はPython `assertAlmostEqual`許容内。最新beta実測: Gold 0.1633313541, US equity 0.3763720963, Japan equity -0.5445438382, US treasury 0.3942646635, Japan bond 0.3634240731。
- 判定: **新API内の数式は合成データで適合。既存main経路は不適合**。
- 対応案: v1計算の本番呼び出し経路を決め、legacy mainの差を解消してから統合テストする。

### 5. σ計算・年率換算

- 要求: 直近52週の単純週次リターンの標本標準偏差×√52。
- 根拠: `layer1/risk_metrics.py:18-23,51-73`; legacy `layer1/volatility.py:20-22`。
- 実際: v1 APIは要求式。legacyは日次log returnのrolling stdで窓120、年率化なし。
- テスト: `test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline formula test, `test_reports_insufficient_history_at_metric_boundaries`。合成fixture期待式/実測はassertAlmostEqualで一致。sigma実測 0.0367486995122495。
- 判定: **新API内は合成データで適合。legacy mainは不適合**。
- 対応案: 本番経路を新APIへ接続し、未annualized legacy出力との意味差を利用者向けに整理する。

### 6. ES計算

- 要求: 直近156週の損失`-R`上位8観測の平均、正値表示。
- 根拠: `layer1/risk_metrics.py:18-23,64-77`; legacy `layer1/volatility.py:25-41`。
- 実際: v1は156個から最大8損失を平均し、実装上は平均値の符号をそのまま返す。legacyは日次log returnのalpha分位点でtailを選び、負符号の値を返す。窓120。仕様には「損失を正値表示」と「top-8(-R)の平均をそのまま取る」の間に、全top-8が利益の場合の符号解釈が残る。
- テスト: v1 formula tests (`test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline) と156週境界テスト。合成fixtureの期待式/実測はassertAlmostEqualで一致、ES実測 0.010943095258152175。
- 判定: **新APIのtop-8計算は合成データで式を確認。表示符号は仕様曖昧さにより未確認。legacy経路は不適合**。
- 対応案: production callerをv1へ統合し、156週以上の入力とstatusを実データで確認。

### 7. ロバスト正規化

- 要求: 対象週を除く過去52週の指標系列でmedian/IQR、linear quantileを一貫使用。IQR閾値以下はnull、未設定thresholdは設定エラー。
- 根拠: `layer1/risk_metrics.py:101-146,194-200`; legacy `layer1/normalize.py:5-15`。
- 実際: v1は直前52のmetric valuesを再計算し当週を除外、`np.quantile(method="linear")`を使用。threshold欠落はnormalization_status=`configuration_error`。threshold自体は設定ファイルに未定義。legacyはrolling window120の窓に当週を含め、IQRゼロだけをNaNにする。
- テスト: `test_normalization_uses_previous_52_metric_values`, `test_iqr_threshold_equality_and_missing_configuration`。等号時null/status、欠落設定statusを確認。sigma normalized実測 -5.708166838169312。テスト側の独立式とassertAlmostEqual一致。
- 判定: **v1アルゴリズムはfixtureで適合、閾値設定と本番接続は不適合/未確認**。
- 対応案: 指標ごとの根拠あるthresholdを実データ分布で決め、config管理する。現時点で推測値を追加しない。

### 8. 7次元ベクトル生成

- 要求: `[σ, ES, β_gold, β_us_equity, β_japan_equity, β_us_treasury, β_japan_bond]`、部分計算と計算状態を保持。
- 根拠: `layer1/risk_metrics.py:10-23,149-200`; `layer1/layer1_vector.py:12-55`。
- 実際: v1 APIは7 metricsとstatus/value/normalizedを返す。legacy builder/mainはsigma, ES, beta_*_norm列の旧構成でfactorにUSDJPYも含む。APIの`as_of`は最後のasset indexだが、W-FRI連続性の検証は行わない。
- テスト: `test_daily_prices_produce_specification_based_weekly_vector`, `test_missing_anchor_keeps_other_daily_price_metrics_available`, risk metrics formula tests。合成fixtureで7項目出力、欠損anchor時もσ/ESと他βを保持。
- 判定: **新APIの単体/合成パイプラインは部分適合。アプリの主出力経路は不適合**。
- 対応案: 実行時入口と出力schemaをv1 vectorに統一し、全statusをUI/APIまで渡す。

### 9. ポートフォリオリターンとベクトル

- 要求: 期初weightsで週次portfolio returnsを計算し、portfolio series自体から7指標を計算。過去保有情報なしは現在構成のscenarioと区別。
- 根拠: `layer1/portfolio.py:20-93`; risk calculator `layer1/risk_metrics.py:149-200`。
- 実際: weights合計1を検証し、missing held returnは週をinvalid、available weightsを再正規化しない。呼出側でportfolio seriesをrisk calculatorに渡す単体例はある。履歴保有データや現在構成scenario metadata、daily→weights→vectorの一体入口はない。
- テスト: `test_uses_each_weeks_beginning_weights` 期待/実測 `[0.052, 0.004, 0.045]`; missing held return, zero-weight missing, sum-to-one, missing weights tests; `test_portfolio_returns_feed_the_existing_risk_vector_calculator` はstatus確認のみ。
- 判定: **return aggregationはunit-test適合。portfolio-to-vector integrationと実績/scenario区別は未確認**。
- 対応案: holdings履歴 schemaかscenario modeを定め、portfolio seriesから全7指標まで確認するintegration testを追加。

### 10. 欠損・異常値・履歴不足

- 要求: 欠損を補完せず、invalid/missing/zero variance/insufficient/config statusesを区別し、計算不能はnullにする。
- 根拠: `layer1/weekly.py:75-109`; `layer1/risk_metrics.py:26-48,60-98,119-146`; portfolio `:58-88`。
- 実際: price stageは欠損/非正値/infを分類。weekly returnは隣接有効価格のみ。risk layerでNaNは`missing_price`、infは`invalid_price`だが、returnの問題にもprice名称を使う。異常な大幅変化の検知はない。`missing_fx` statusは実装/接続なし。
- テスト: weekly missing gap/non-positive/duplicate/final missing tests; risk insufficient history, missing returns, zero variance, missing anchor, malformed date; portfolio missing/no renormalization tests。全件pass。
- 判定: **一部適合**。補完抑止/主要statusはfixture検証済み。異常変化・FX欠損・return status namingは未対応/未確認。
- 対応案: 異常変化の閾値は設定方針を確定後に追加し、statusをprice/return/fx段階で明確にする。

### 11. 単体・統合テスト

- 要求: 数式、境界、欠損、currency、portfolio、normalization warmup、再現性を独立に検証。
- 根拠: `tests/test_layer1.py`, `test_weekly.py`, `test_risk_metrics.py`, `test_portfolio.py`, `test_layer1_pipeline.py`, `test_fetch_csv.py`。
- 実際: 34 testsすべてpass。旧Layer1回帰8件は旧挙動を固定し、log return/120日window/fillの期待も含む。新fixture testsは式の一部を実装と同型のNumPy式で照合する。USD/FX、調整後価格、実データ、portfolio full vector、data→UIのテストはなし。
- 期待値/実測: pytest/unittest log上34 success, 0 fail, 0 error。synthetic sigma/ES/betas数値は上記各項目を参照。
- 判定: **テスト実行はpass、仕様カバレッジは未完**。
- 対応案: currency conversion・portfolio full vector・data-quality・UI接続のテストを統合後に追加。独立した数式fixtureも用意する。

### 12. UIと実計算結果の接続

- 要求: 7軸、元値/正規化値、β符号、nullと理由、portfolio合成vector、実データ状態を表示。
- 根拠: `reports/risk-vector-preview.html`（静的プレビュー）。計算/UI接続コードは確認できず。
- 実際: HTMLプレビューは合成データの静的表示で、risk calculatorや取得データから生成していない。ラベルとしてGold/US Equity/Japan Equity/US Treasury/Japan Bondを表示するが、data pipeline接続なし。
- テスト: UI/API integration testなし。previewの静的内容はunit test対象外。
- 判定: **未実装／未確認**。
- 対応案: 計算出力schemaと実データ状態が固まった後、UIへ接続し、null/status/FX含む値をfixtureで画面検証する。

## 4. 主要な合成fixture照合値

fixture: `tests/test_risk_metrics.py::make_weekly_returns`、220週の決定論的合成週次リターン。観測値は2020-01-03からのW-FRI系列。期待値は同テストの式（標本std・top 8 loss・sample cov/sample var）を用いた。

| 指標 | 期待式 | 実測値 | テスト結果 |
|---|---|---:|---|
| σ | `std(last52, ddof=1) * sqrt(52)` | 0.0367486995122495 | assertAlmostEqual pass |
| ES | `mean(sort(-last156)[-8:])` | 0.010943095258152175 | assertAlmostEqual pass |
| β Gold | `cov(last52 asset,gold)/var(gold)` | 0.16333135412799465 | assertAlmostEqual pass |
| β US equity | 同上 | 0.3763720963166546 | assertAlmostEqual pass |
| β Japan equity | 同上 | -0.5445438381597948 | assertAlmostEqual pass |
| β US Treasury | 同上 | 0.394264663499942 | assertAlmostEqual pass |
| β Japan bond | 同上 | 0.3634240730965663 | assertAlmostEqual pass |
| σ正規化 | `(current - median(prior52σ))/IQR(prior52σ)` linear quantile | -5.708166838169312 | assertAlmostEqual pass |

portfolio fixture期待/実測: `[0.052, 0.004, 0.045]`（各週の開始時weight × asset return和）。week holiday fixture期待/実測: `110/100-1 = 0.1`。

これらは実計算関数とNumPyを使った合成fixtureの検算であり、独立した実装系や市場データとの照合ではない。

## 5. データ取得からUIまでの確認済みフロー

確認済みの部品接続は次の通り:

```text
Yahoo Finance (未実行・未検証)
  -> fetch/fetch_csv.py (CloseをCSV保存、delta merge)
  -> 手動で価格表をbuild_risk_vector_from_daily_pricesへ渡す
  -> weekly.build_weekly_returns (同一通貨の前提)
  -> risk_metrics.calculate_risk_vector
```

ポートフォリオは別経路:

```text
weekly asset returns + beginning weights
  -> portfolio.calculate_portfolio_returns
  -> risk_metrics.calculate_risk_vector (unit testから直接呼ぶ)
```

`fetch_csv.main`からv1計算へ自動接続するrunnerは確認できない。USD/JPY換算部品もない。risk vectorからHTML previewへの接続もない。

## 6. 既知の問題・確認事項・残存リスク

1. **FX仕様不足**: FX観測日を米国価格日にどう揃えるか、休日・市場終値時刻・欠損時処理が未決。変換なしで円換算を満たしたことにはならない。
2. **adjusted close未確認**: Downloaderは`Close`を保存。指数とETFの配当・分配金定義の整合性が未確認。
3. **incremental fetch未実データ確認**: downloaderをfakeに置き換えたoffline testのみ。Yahooの実応答形式、ticker別十分な履歴、改定/分割/欠落処理は未確認。
4. **legacy mainが旧仕様**: `layer1/layer1_vector.py:58-81,84-135`はdaily log-return・旧窓・旧factor構成で出力。新v1 APIは追加されたがmainを置換していない。
5. **閾値未設定**: `config/tickers.yaml`にIQR thresholdなし。thresholdなしではraw metricは計算されるがnormalized値はconfiguration_error。
6. **portfolio mode不在**: 実際の保有履歴・scenario modeの出力状態を表す契約なし。
7. **price/return status語彙**: `risk_metrics`はreturn配列のNaN/infにも`missing_price`/`invalid_price`を返す。段階別状態をUIに出す設計は未接続。
8. **週次入力契約**: `calculate_risk_vector`はDatetimeIndex重複を拒否するが、各行が連続W-FRIであるか検証しない。呼出元がweekly出力を渡す前提。
9. **UI未接続**: HTMLはstatic synthetic preview。
10. **監査提出経路**: Feel2専用連携も閲覧権も未確認。ローカルreportの可視性はFeel2側で確認が必要。
11. **ES表示符号の仕様曖昧さ**: 正値表示という文言と、top-8損失の平均を無変換で返す式が、全tail週が利益の場合に一致しない。製品表示の符号方針は監査役/仕様責任者の判断が必要。

## 7. Feel2レビュー依頼時に確認してほしい事項

- FX同期・価格調整方針が仕様を満たす最小実装として十分に定義されているか。
- downloaderの5年 bootstrap (`208 + 52` weeks) とcoverage条件に不足がないか。
- daily-to-weeklyの欠損週判定とrisk calculatorの週次index前提をどう接続すべきか。
- `missing_price`/`invalid_price`をreturn inputのエラーにも使うstatus設計の妥当性。
- portfolio seriesからvectorを作るAPI、履歴実績とscenario modeの出力契約。
- legacy `main()`を維持したままv1を統合する最小移行案。

**この資料作成時点ではFeel2監査結果なし。コード変更は行っていない（本資料の追加を除く）。修正段階には進んでいない。**
