# RVE v1.0 再監査証跡（2026-10-25）

状態: **実装・検証中。仕様適合完了ではない。Feel2による独立監査前。**
対象: `watag/RVE-pjt`、`agent/rve-v1.0-audit`、PR #6。基点コミット `7fd22b2a77d37dcdd02064cea2f911635d4432e2`。このワークツリーでは以下の変更は未コミット・未push。PR/CIは更新後の差分をまだ評価していない。

## Git保全

- PR用の別worktree `/tmp/rve-v1.0-audit` を使用。元worktree `/root/work/rve` のRunner変更と `.agent-state/` は触っていない。
- PR worktree差分: `.github/workflows/ci.yml`, `config/tickers.yaml`, `docs/rve-v1.0-spec.md`, `fetch/fetch_csv.py`, `layer1/{fx,layer1_vector,portfolio,weekly}.py`, `reports/risk-vector-preview.html`, `reports/risk-vector-preview.js`, `scripts/calibrate_iqr_thresholds.py`, `tests/{test_fetch_csv,test_fx,test_iqr_calibration,test_layer1_pipeline,test_portfolio,test_risk_metrics,test_ui_preview.js}` および本報告・校正報告。
- 未追跡の一時データ、Playwright browser、スクリーンショットは `/tmp` 配下。リポジトリには含めていない。

## 仕様判断の反映

ユーザー決定を仕様書に反映した: ESは`mean(top8(-R))`の符号を維持し負値も許す。USD/JPYは同じ取引日終値を厳密一致し、補完しない。IQR閾値は5年の実データに基づく正の過去IQR分布の5パーセンタイル（linear）とする。v1 portfolioはロングオンリーで負ウェイトを拒否する。

## 検証結果

| 検証 | 実行結果 | 範囲・限界 |
|---|---|---|
| Python全テスト | `PYTHONPYCACHEPREFIX=/tmp/rve-v1-pycache /tmp/rve-layer1-ubuntu-venv/bin/python -m unittest discover -s tests -v` — **72件成功、失敗0** | Python 3.12、NumPy 2.4.3、pandas 3.0.1、PyYAML 6.0.3。合成/fixtureテスト |
| Python compile | `python -m compileall -q layer1 fetch scripts tests` — 成功 | 構文検査のみ |
| Node UI tests | `node --test tests/test_ui_preview.js` — **7件成功、失敗0** | UIロジック。Node 18.19.1。CI定義はNode 22 |
| JS syntax | `node --check reports/risk-vector-preview.js` — 成功 | ブラウザ描画の完全検証ではない |
| 差分空白検査 | `git diff --check` — 成功 | 現在のPR用worktree |
| Yahoo実取得 | `fetch_and_save`で7系列（Toyota、5アンカー、JPY=X）の初回取得成功 | 出力先 `/tmp/rve-fetcher-live-check`。実行日2026-10-25、履歴品質・失敗時保全を本番データで包括検証したものではない |
| 5年校正 | 2021-10-25〜2026-10-23のYahoo/yfinance取得系列で校正CLI実行、7閾値を設定 | 6資産系列（Toyota+5アンカー）で、将来の広い銘柄群の代表性は未確立。報告は `reports/rve-v1.0-iqr-calibration.md` |
| 実データ計算 | `main()`を一時コピーの実系列に対して実行。2026-10-23時点で7生指標と7正規化指標がすべて`ok` | 出力JSONは`/tmp/rve-v1-calibration/output/7203.T_risk_vector.json`。ポートフォリオ未設定 |
| 実ブラウザ | **未実施** | Playwright Chromiumは取得したが、起動に`libnspr4.so`が必要で失敗。OSパッケージ導入や権限回避は実施せず |
| GitHub Actions | **更新後コミットでは未実施** | 既知のCI成功は更新前SHAに対するもの。ブランチ未pushなので新CI結果なし |

### 実計算スナップショット（Toyota）

| 指標 | 生値 | 状態 |
|---|---:|---|
| sigma | 0.2671797545634205 | ok |
| ES | 0.08152291829932985 | ok |
| beta_gold | 0.13270293768019742 | ok |
| beta_us_equity | 0.1417383865022261 | ok |
| beta_japan_equity | 0.7078389984439125 | ok |
| beta_us_treasury | 0.5448457529242493 | ok |
| beta_japan_bond | 0.26911327528853324 | ok |

これはYahoo履歴の単一取得時点による再現証跡で、データ提供者が過去値を改訂した場合は同一値を保証しない。正規化値も当該系列に対する計算結果で、銘柄間の絶対リスク比較値ではない。

## 変更と監査指摘の対応

- **IQR**: `scripts/calibrate_iqr_thresholds.py`, `config/tickers.yaml`, `reports/rve-v1.0-iqr-calibration.md`, `tests/test_iqr_calibration.py`。7閾値を設定し、q05校正规則・単位・対象データ・制限を記録。閾値は現構成ユニバースに依存。
- **ES符号**: `layer1/risk_metrics.py`の符号付き定義を変更せず、仕様とUIで負値も表示。all-profit/all-loss/mixed/missing testsを追加。
- **FX/週次整列**: `layer1/fx.py`, `layer1/weekly.py`でsource-local session dateを保持、完全一致のみ。FX欠損を補完せず`missing_fx`を伝播。タイムゾーン変換規則と時差の経済的影響は残存リスク。
- **Portfolio**: `layer1/portfolio.py`, `layer1/layer1_vector.py`で負ウェイト、合計不正、日付/銘柄/リターン欠損を理由付きで拒否し、欠損週で再加重しない。`portfolio: null`は`not_configured`。実保有履歴は提供されていない。
- **取得品質**: `fetch/fetch_csv.py`で欠損/非有限/非正価格を拒否し、無効入力で履歴を置換しないテストを追加。実取得7系列は成功したが、Yahooの長期品質・調整価格意味・レート制限を尽くしたものではない。
- **UI**: `reports/risk-vector-preview.js`が生成JSONを読み、raw/normalized/status、負βとnull、portfolio未設定/エラーを描画。nodeロジックテストは通過。実ブラウザ/Pages成果物確認は未完了。
- **CI**: `.github/workflows/ci.yml`にPython 3.12固定依存のオフラインテストとNode 22ロジックテストを定義。更新差分のGitHub Actions結果はまだない。

## 再現コマンド

```sh
python -m unittest discover -s tests -v
python -m compileall -q layer1 fetch scripts tests
node --test tests/test_ui_preview.js
node --check reports/risk-vector-preview.js
git diff --check
```

実ネットワーク検証は `python fetch/fetch_csv.py` を既定パスで実行するとリポジトリ内データを変更するため、本報告の再現では一時出力先を指定した`fetch_and_save`を使用した。校正CLIは `python scripts/calibrate_iqr_thresholds.py --data-dir <取得履歴> --output <一時JSON>`。

## 残存事項

1. 実ブラウザ描画とGitHub Pages上のJSON配置を確認していない。
2. CI結果は古いコミットのものしかなく、現差分はGitHub Actions未実行。
3. 実績ウェイト/current holdingsのデータがなく、portfolio統合の市場実データ検証なし。
4. Yahooの価格フィールド、配当調整の意味、FXの異なる市場終値時刻が将来の銘柄群に十分か、独立監査とデータ責任者の確認が必要。
5. 異常な価格変化の数値閾値は未定義で未実装。正の価格・欠損・重複検査はある。
6. 既存CSV外部利用者がJSON出力への変更から受ける影響は未確認。
7. Feel2の独立監査は未実施。仕様適合完了とは宣言しない。
