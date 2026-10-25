# RVE v1.0 監査再現ガイド

このPRはRVE v1.0の実装と検証証跡をまとめる。未確定の閾値やES表示規則、実市場データで未検証の挙動は完了扱いしない。

## 環境とテスト

最終ローカル実行はPython 3.12.3 / NumPy 2.5.4 / pandas 3.0.6 / PyYAML 6.0.3。一時仮想環境での実行で、NumPy/pandasはrequirements.txtの固定版（2.4.3 / 3.0.1）と異なる。CIはこれら3パッケージを固定しているが、GitHub Actionsの実行結果は未確認。ローカルで宣言依存関係から再現する場合:

```sh
python -m unittest discover -s tests -v
python -m py_compile fetch/fetch_csv.py layer1/*.py tests/*.py
git diff --check
```

現在の結果は59件成功、失敗0件。テストは合成データまたはfake downloaderを用いるオフラインテストである。Yahoo Financeの実取得や実市場価格の品質は確認していない。

## 計算結果の生成とUI

`python fetch/fetch_csv.py`で設定した`price_field`（ETF等は`Adj Close`、`^GSPC`は`Close`）を取得し、CSV内の価格列名は`Close`に統一する。調整方式の異なる履歴は`TICKER.Adj_Close.csv`等へ分離し、既存`TICKER.csv`を混在更新しない。`python layer1/layer1_vector.py`は通常実行経路でconfigのrole=asset銘柄についてv1 APIを呼び、`data/layer1/TICKER_risk_vector.json`を書き出す。`reports/risk-vector-preview.html`はToyotaのJSONを読み、値とステータスを表示する。JSONがない場合はサンプル値に置き換えず、結果なしと表示する。

USD資産と`JPY=X`は完全一致する暦日で結合する。FX価格を前方補完せず、欠損は`missing_fx`としてリスク指標まで伝播する。FX市場と株式市場の終値時刻・タイムゾーン差を吸収する規則は未確定で、実データによる確認が必要。

`config/tickers.yaml`のIQR閾値は`null`のままであり、正規化値は`configuration_error`となる。閾値を確定するには代表性のある価格履歴による校正が必要。ポートフォリオのAPIは実績ウェイト系列と、現在ウェイト固定のシナリオを区別する。実績モードは`symbols`と`weights_file`、シナリオモードは`current_weights`を設定する。現行設定には保有ウェイトがないため、通常実行ではポートフォリオベクトルを出力しない。

## データ取得を実行する場合

`python fetch/fetch_csv.py`はYahoo Financeへアクセスし、`config/tickers.yaml`記載の銘柄を`data/processed/`へ保存する。これは実ネットワークを使い外部価格データを取得する操作であり、このPR作成時には実行していない。`data/raw/`と`data/processed/`のCSVや秘密情報はPRに含めない。

## 主な証拠ファイル

- 規範: `docs/rve-v1.0-spec.md`
- 差分評価、テスト証拠、未確認事項: `reports/rve-v1.0-audit-draft.md`
- 増分取得: `fetch/fetch_csv.py` と `tests/test_fetch_csv.py`
- 週次/品質: `layer1/weekly.py` と `tests/test_weekly.py`
- σ/ES/β/正規化/ベクトル: `layer1/risk_metrics.py` と `tests/test_risk_metrics.py`, `tests/test_layer1_pipeline.py`
- portfolio: `layer1/portfolio.py` と `tests/test_portfolio.py`
- 旧Layer 1の回帰挙動: `layer1/{beta,volatility,normalize,layer1_vector}.py` と `tests/test_layer1.py`
- 表示: `reports/risk-vector-preview.html`（実行結果JSONをfetchし、nullと状態を表示。ブラウザ/Pagesでの実表示は未検証）
