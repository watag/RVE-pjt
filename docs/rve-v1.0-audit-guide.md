# RVE v1.0 監査再現ガイド

現行の検証結果・残課題は [再監査証跡](../reports/rve-v1.0-reaudit.md) を参照してください。旧監査ドラフトは履歴資料であり、現状のテスト件数や確認状態を表しません。

## オフライン検証

Python 3.12、NumPy 2.4.3、pandas 3.0.1、PyYAML 6.0.3、およびNode.js 22を使います（GitHub ActionsのCI定義と同じバージョン）。リポジトリルートから:

```sh
python -m unittest discover -s tests -v
python -m compileall -q layer1 fetch scripts tests
node --test tests/test_ui_preview.js
node --check reports/risk-vector-preview.js
git diff --check
```

実データ取得と校正の方法、校正対象・閾値の限界は [校正報告](../reports/rve-v1.0-iqr-calibration.md) に記載しています。合成テストとYahoo実データの観測は区別してください。実ブラウザおよびPagesでの表示は未確認です。

## 主な根拠

- 規範仕様: `docs/rve-v1.0-spec.md`
- 再監査証跡: `reports/rve-v1.0-reaudit.md`
- IQR校正: `reports/rve-v1.0-iqr-calibration.md`
- 増分取得・品質: `fetch/fetch_csv.py`, `tests/test_fetch_csv.py`
- FX/週次整列: `layer1/fx.py`, `layer1/weekly.py`, `tests/test_fx.py`, `tests/test_weekly.py`
- σ/ES/β/正規化: `layer1/risk_metrics.py`, `tests/test_risk_metrics.py`
- portfolio: `layer1/portfolio.py`, `tests/test_portfolio.py`
- main-to-JSON: `layer1/layer1_vector.py`, `tests/test_layer1_pipeline.py`
- UI: `reports/risk-vector-preview.html`, `reports/risk-vector-preview.js`, `tests/test_ui_preview.js`
- CI: `.github/workflows/ci.yml`

取得結果は時点依存であり、今回の一時データ・ブラウザキャッシュはコミットされていません。
