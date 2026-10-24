# RVE v1.0 監査再現ガイド

このPRは監査用スナップショットである。計算・データ取得・UIの統合が完了したという意味ではない。

## 環境とテスト

再実行環境はPython 3.12.3 / NumPy 2.5.4 / pandas 3.0.6の一時仮想環境。`requirements.txt`が指定するNumPy 2.4.3 / pandas 3.0.1とは異なる版であり、この環境では依存関係を再インストールしていない。よってテスト成功は記録環境の結果で、requirements.txtの全ピンに対する確認ではない。ローカルで宣言依存関係から再現する場合:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile fetch/fetch_csv.py layer1/*.py tests/*.py
```

この監査ランでは`PATH=/tmp/rve-layer1-ubuntu-venv/bin:$PATH PYTHONPYCACHEPREFIX=/tmp/rve-v1-audit-pycache python -m unittest discover -s tests -v`を実行し、34 tests passed、0 failedを確認した。テスト名と実行ログは`reports/rve-v1.0-test-log.txt`。構文検査は`PATH=/tmp/rve-layer1-ubuntu-venv/bin:$PATH PYTHONPYCACHEPREFIX=/tmp/rve-v1-audit-pycache python -m py_compile fetch/fetch_csv.py layer1/*.py tests/*.py`で成功した。全テストは合成またはfake downloaderを用いるオフラインテストである。Yahoo Financeの実取得や実市場価格の品質は確認していない。

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
- 表示例: `reports/risk-vector-preview.html`（静的な合成データのプレビューで、計算器とは接続されていない）
