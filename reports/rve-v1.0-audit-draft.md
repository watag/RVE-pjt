# RVE v1.0 仕様適合監査資料（Feel2提出用ドラフト）

更新日: 2026-10-25
対象リポジトリ: `watag/RVE-pjt`
監査ブランチ: `agent/rve-v1.0-audit`（PR #6、base `main`）
比較対象main: `cfe8b56d893f133836d113a3184cd8ecd49e3c99`
監査状態: Feel2未提出・未監査。本資料は仕様適合の宣言ではない。

この更新はPR #6のスナップショット後に最新mainを取り込み、RVE計算・テスト・UIの実装を進めた状態を記録する。PRは未マージ。独立監査と実市場データの確認は未実施。

## 1. 作業状態と保全

調査開始時の状態:

- 作業は専用worktree `/tmp/rve-v1.0-audit` の `agent/rve-v1.0-audit` で実施。
- 元worktreeのRunner変更と `.agent-state/` は変更・追加していない。
- 最新mainに含まれていたCI、`data/layer1/7203.T_layer1.csv`、`tests/test_rve_core.py`を保持。
- `data/processed/` に実価格履歴はなく、実市場データの計算・品質は未検証。

Feel2の独立レビュー結果は含まない。GitHub PR上の公開により監査役が参照できる状態を用意するが、Feel2が当該リポジトリへアクセス可能か、および監査依頼を受領したかは未確認。

## 2. 実行した検証

実行環境: `/tmp/rve-layer1-ubuntu-venv`、Python 3.12.3、NumPy 2.5.4、pandas 3.0.6、PyYAML 6.0.3。最終実行:

```text
PYTHONPYCACHEPREFIX=/tmp/rve-v1-audit-pycache /tmp/rve-layer1-ubuntu-venv/bin/python -m unittest discover -s tests -v
```

結果: 59 tests, `OK`。NumPy/pandasはrequirementsの固定版ではない。CIはNumPy 2.4.3、pandas 3.0.1、PyYAML 6.0.3を使う設定にしたが、GitHub Actionsでの実行結果はまだない。

同じ作業段階で `python -m py_compile fetch/fetch_csv.py layer1/*.py tests/*.py`、`git diff --check`、一時抽出したUI scriptへの`node --check`も成功。59件は合成データ、fixture、fake downloaderによるオフラインテストで、実価格取得を意味しない。

## 3. 仕様適合表

### 1. 価格データ取得・差分更新

- 要求: 設定された5アンカーと対象銘柄を取得し、2年固定上書きではなく履歴を維持する増分更新を行う。
- 根拠: `fetch/fetch_csv.py:9-14,59-100,103-148`; `config/tickers.yaml:1-23`。
- 実際: 初回履歴は260週前から取得し、既存履歴は最終日から7日重複して差分取得。重複範囲の新値を優先し履歴を保持する。銘柄ごとに`price_field`を設定し、`Adj Close`と`Close`は異なるCSVへ保存して混在を防ぐ。空取得・不正日付・同一入力内の日付重複は例外にし、既存ファイルを書き換えない。
- テスト: `test_first_fetch_backfills_five_year_warmup`, `test_mature_history_updates_from_recent_overlap`, `test_merge_preserves_history_and_replaces_overlapping_dates`, `test_empty_download_fails_without_rewriting_existing_history`, `test_adjusted_history_does_not_overwrite_legacy_close_history`等。合計9 fetchテストpass。
- 判定: **ローカルfixture適合／実Yahoo未確認**。`^GSPC`は`Close`、ETF/個別株は`Adj Close`を指定。データソースはYahoo Finance固定。実応答・各銘柄の調整系列の意味は未検証。
- 対応案: 実データ取得後に利用可能履歴・adjusted price定義・取得失敗を確認する。指数価格リターンとETF調整後リターンの定義差は残る。

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
- 実際: `layer1/fx.py::convert_usd_prices_to_jpy`がUSD価格×JPY per USDを同じ暦日で変換。前方補完せず、FX欠損は`missing_fx`、存在する不正レートは`invalid_price`。`main()`はUSDアンカー価格を変換してから週次化し、JPY=Xをβ軸に加えない。
- テスト: `test_converts_prices_before_weekly_return_calculation`で100×150→110×155、円価格15000→17050、単純リターン13.6667%。`test_missing_fx_is_not_filled_and_remains_distinct`、`test_same_calendar_date_matches_different_intraday_timestamps`、main→β統合fixtureもpass。
- 判定: **合成データで実装経路を確認／市場日付同期は未確認**。
- 対応案: 現在は暦日一致を実装契約とした。市場終値時刻・タイムゾーン・休場日の扱いが仕様に定義されていないため、実データで検証し仕様決定する。

### 4. β計算

- 要求: 週次単純リターン、各5アンカー独立単回帰、直近52週、切片ありOLSの傾きと同じ。
- 根拠: v1 `layer1/risk_metrics.py:79-98,149-200`; legacy `layer1/beta.py:20-54`。
- 実際: v1は標本共分散/標本分散を52週で計算し、アンカー別statusを返す。legacyは日次log return、既定120、anchorをffill/bfillし、sample covariance/population varianceを使用。
- テスト: `test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline `test_daily_prices_produce_specification_based_weekly_vector`, `test_zero_variance_anchor_has_its_own_status`, 欠損/アンカー設定テスト。合成fixtureの期待式と実測差はPython `assertAlmostEqual`許容内。最新beta実測: Gold 0.1633313541, US equity 0.3763720963, Japan equity -0.5445438382, US treasury 0.3942646635, Japan bond 0.3634240731。
- 判定: **新APIの数式と通常main経路を合成データで確認**。互換目的のlegacy計算関数はimport可能だが、Layer 1の実行入口では使用しない。
- 対応案: 実価格系列で5アンカーの時刻整列・分散・βを確認する。

### 5. σ計算・年率換算

- 要求: 直近52週の単純週次リターンの標本標準偏差×√52。
- 根拠: `layer1/risk_metrics.py:18-23,51-73`; legacy `layer1/volatility.py:20-22`。
- 実際: v1 APIは要求式。legacyは日次log returnのrolling stdで窓120、年率化なし。
- テスト: `test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline formula test, `test_reports_insufficient_history_at_metric_boundaries`。合成fixture期待式/実測はassertAlmostEqualで一致。sigma実測 0.0367486995122495。
- 判定: **新APIと通常main経路は合成データで確認**。legacy helper関数は旧仕様のまま残すがmainから呼ばれない。
- 対応案: 出力単位・CSVからJSONへの移行影響を利用者へ案内し、実データで再検証する。

### 6. ES計算

- 要求: 直近156週の損失`-R`上位8観測の平均、正値表示。
- 根拠: `layer1/risk_metrics.py:18-23,64-77`; legacy `layer1/volatility.py:25-41`。
- 実際: v1は156個から最大8損失を平均し、実装上は平均値の符号をそのまま返す。legacyは日次log returnのalpha分位点でtailを選び、負符号の値を返す。窓120。仕様には「損失を正値表示」と「top-8(-R)の平均をそのまま取る」の間に、全top-8が利益の場合の符号解釈が残る。
- テスト: v1 formula tests (`test_calculates_annualized_sigma_es_and_five_anchor_betas`, pipeline) と156週境界テスト。合成fixtureの期待式/実測はassertAlmostEqualで一致、ES実測 0.010943095258152175。
- 判定: **top-8(-R)計算を合成データで確認。表示符号の矛盾は未解決**。値は式の符号をそのまま保持し、UIも正値へ強制変換しない。
- 対応案: 仕様責任者が「式の平均値を保持」か「表示時に正値化」か決定する。実装は決定待ち。

### 7. ロバスト正規化

- 要求: 対象週を除く過去52週の指標系列でmedian/IQR、linear quantileを一貫使用。IQR閾値以下はnull、未設定thresholdは設定エラー。
- 根拠: `layer1/risk_metrics.py:101-146,194-200`; legacy `layer1/normalize.py:5-15`。
- 実際: v1は直前52個のmetric valuesを再計算し当週を除外、`np.quantile(method="linear")`を使用。configに7指標の閾値キーを置き、値は全てnull。nullは`configuration_error`となる。legacy normalization helperは旧呼出し互換のため残り、v1 mainからは呼ばれない。
- テスト: `test_normalization_uses_previous_52_metric_values`, `test_iqr_threshold_equality_and_missing_configuration`。等号時null/status、欠落設定statusを確認。sigma normalized実測 -5.708166838169312。テスト側の独立式とassertAlmostEqual一致。
- 判定: **計算窓/対象週除外/statusはfixtureで確認。正規化値は未出力**。
- 対応案: 実系列の単位・分布を調べ閾値を仕様決定する。根拠がない数値は追加していない。

### 8. 7次元ベクトル生成

- 要求: `[σ, ES, β_gold, β_us_equity, β_japan_equity, β_us_treasury, β_japan_bond]`、部分計算と計算状態を保持。
- 根拠: `layer1/risk_metrics.py:10-23,149-200`; `layer1/layer1_vector.py:12-55`。
- 実際: `layer1_vector.main()`はdaily prices→FX換算→weekly returns→`calculate_risk_vector`を実行し、7指標の値/status/normalizedをJSONへ書く。通常mainにlegacy log-return経路はない。旧builder関数はimport互換のため残す。通常出力形式は旧CSVからJSONへ変更。W-FRI生成はmain側で行う。
- テスト: `test_daily_prices_produce_specification_based_weekly_vector`, `test_missing_anchor_keeps_other_daily_price_metrics_available`, risk metrics formula tests。合成fixtureで7項目出力、欠損anchor時もσ/ESと他βを保持。
- 判定: **合成fixtureで通常main→7指標JSONを確認。実価格で未検証**。
- 対応案: 既存CSVの外部利用者がいれば新JSON schemaへ移行が必要。リポジトリ内に旧CSVを読む利用者は見つからず、既存CSVファイル自体は保持した。

### 9. ポートフォリオリターンとベクトル

- 要求: 期初weightsで週次portfolio returnsを計算し、portfolio series自体から7指標を計算。過去保有情報なしは現在構成のscenarioと区別。
- 根拠: `layer1/portfolio.py:20-93`; risk calculator `layer1/risk_metrics.py:149-200`。
- 実際: `calculate_portfolio_risk_vector`がポートフォリオの合成週次リターンからrisk calculatorを呼ぶ。`realized`は週別期初ウェイト、`scenario`は現在ウェイトSeriesを全履歴へ適用しmodeを返す。欠損active holdingは無効化し再配分しない。mainはconfigのportfolio設定がある場合のみ計算。
- テスト: `[0.052, 0.004, 0.045]`の手計算、欠損・ゼロウェイト・比率合計、実績ウェイト系列とシナリオ固定比率からのσを検証。main統合テストも1資産のscenario vectorを検証。
- 判定: **合成データの実績/scenario APIを確認。保有データなしのため実ポートフォリオは未検証**。
- 対応案: 実保有履歴/current weightsの入力ファイルと定期リバランス規則を確定する。

### 10. 欠損・異常値・履歴不足

- 要求: 欠損を補完せず、invalid/missing/zero variance/insufficient/config statusesを区別し、計算不能はnullにする。
- 根拠: `layer1/weekly.py:75-109`; `layer1/risk_metrics.py:26-48,60-98,119-146`; portfolio `:58-88`。
- 実際: fetchは空取得・不正日付・同じ入力内の重複日付を拒否。weeklyは非正値、欠損週、FX由来statusを保持。risk metricsは不足履歴、missing price/FX、invalid price、zero variance、configuration errorを個別に返す。大幅変化の異常値基準は未定。
- テスト: fetch/FX/weekly/risk/portfolioの欠損・異常・境界fixtureがpass。59件中これら関連テストを含む。
- 判定: **fixtureで主要状態を確認。異常リターン基準と実市場系列は未確認**。
- 対応案: 異常変化の数値閾値、return status語彙の粒度を仕様決定する。

### 11. 単体・統合テスト

- 要求: 数式、境界、欠損、currency、portfolio、normalization warmup、再現性を独立に検証。
- 根拠: `tests/test_layer1.py`, `test_weekly.py`, `test_risk_metrics.py`, `test_portfolio.py`, `test_layer1_pipeline.py`, `test_fetch_csv.py`。
- 実際: 最終ローカル実行59件pass。旧Layer1 helper回帰も保持し、FX円換算・status伝播・価格basis分離・main JSON・portfolio realized/scenarioを追加検証。GitHub Actions未実行。
- 期待値/実測: USD 100×150→JPY 15000、110×155→17050、return 13.6667%; portfolio scenario/realized σは独立式と`assertAlmostEqual`一致。詳細な7指標fixtureは上表。
- 判定: **合成fixtureの実装経路を検証。CI・実市場データ・ブラウザ表示は未確認**。
- 対応案: PR上でCIを確認し、実データ取得とPages表示は別途実施する。

### 12. UIと実計算結果の接続

- 要求: 7軸、元値/正規化値、β符号、nullと理由、portfolio合成vector、実データ状態を表示。
- 根拠: `reports/risk-vector-preview.html`; JSON producer `layer1/layer1_vector.py::main`。
- 実際: HTMLは`../data/layer1/7203.T_risk_vector.json`をfetchし、7指標のstatus、null、β符号、normalized値を描画。JSONなし時にサンプル値へfallbackしない。portfolio未設定も明示。
- テスト: main統合fixtureが出力JSONを読むところまで検証。実ブラウザ、GitHub Pagesの公開パス、実データの視覚確認は未実施。
- 判定: **データschema接続は実装。ブラウザ/Pages表示は未検証**。
- 対応案: 出力JSONをPages artifactに含め、実ブラウザでstatus/負β/null表示を確認する。

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

実装した処理経路は次の通り:

```text
Yahoo Finance (未実行・未検証)
  -> fetch/fetch_csv.py (設定price_field、別basis CSV、履歴merge)
  -> layer1_vector.main (CSV load、USD*JPY、weekly)
  -> risk_metrics.calculate_risk_vector
  -> data/layer1/7203.T_risk_vector.json
  -> reports/risk-vector-preview.html (JSON fetch)
```

ポートフォリオは別経路:

```text
weekly asset returns + realized/scenario beginning weights
  -> portfolio.calculate_portfolio_returns
  -> portfolio.calculate_portfolio_risk_vector
  -> risk_metrics.calculate_risk_vector
```

mainは価格取得後に実行する。現在のconfigには保有ウェイトがないため、mainの標準出力はportfolio vectorを含めない。

## 6. 既知の問題・確認事項・残存リスク

1. **FX暦日同期**: 実装は同じ暦日のレートのみ利用。市場終値時刻・休場時の代替規則は未確定で実データ未検証。
2. **価格basis**: ETF等はAdj Close、`^GSPC`はClose。指数と分配金調整ETFのリターン定義差は残る。
3. **実データ取得**: Yahooへの実通信・利用可能履歴・実系列の品質は未確認。
4. **IQR閾値**: configの全閾値はnull。正規化はconfiguration_errorとなり、値は未出力。
5. **ES表示符号**: top-8(-R)平均と正値表示の記述が、top 8全て利益の場合に曖昧。修正待ち。
6. **Portfolio holdings**: APIはrealized/scenarioを区別するが実保有履歴・現在ウェイトは未提供。
7. **異常リターン基準**: 非正値・欠損・重複を検査するが、大幅変化の判定閾値は仕様決定待ち。
8. **出力互換性**: mainの通常出力はlegacy CSVからJSONへ変更。リポジトリ内のCSV readerは見つからず、CSVファイル自体は保持した。外部利用者への移行影響は未確認。
9. **UI公開**: HTMLはJSON接続済み。PagesへのJSON配置・実ブラウザ描画は未確認。
10. **CI**: main向けworkflowと固定依存版を追加した。PRのActions実行結果は未確認。
11. **監査**: Feel2の独立監査結果はまだない。

## 7. Feel2レビュー依頼時に確認してほしい事項

- FX同期・価格調整方針が仕様を満たす最小実装として十分に定義されているか。
- downloaderの5年 bootstrap (`208 + 52` weeks) とcoverage条件に不足がないか。
- daily-to-weeklyの欠損週判定とrisk calculatorの週次index前提をどう接続すべきか。
- `missing_price`/`invalid_price`をreturn inputのエラーにも使うstatus設計の妥当性。
- portfolio weights fileのschema、期初時点、scenario modeの明示方法。
- ES符号の矛盾とIQR閾値の設定根拠。
- main出力JSONへの移行が外部利用者へ与える影響。

**この更新は監査用実装・テストの変更後の状態を記録する。Feel2監査結果はなく、仕様適合を完了したとは判断しない。**
