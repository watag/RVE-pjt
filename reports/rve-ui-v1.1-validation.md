# RVE UI v1.1 validation record

## Scope

This record covers the UI and history presentation changes for RVE UI v1.1. It does not claim complete RVE v1.0 specification compliance.

## Implementation and data contract

- `reports/risk-vector-preview.html` provides separate individual and portfolio tabs.
- `reports/risk-vector-preview.js` renders signed five-anchor beta sensitivity, σ/ES cards, normalized histories, and raw-beta histories. Values with a non-`ok` status are omitted from charts rather than converted to zero. The beta display range is fixed at −3 to +3; only chart coordinates are clipped, while the measured value remains in the table and tooltip.
- The JSON contract keeps the latest `asset` and `portfolio` objects and adds `asset_history`, `portfolio_history`, and `portfolio_holdings`. A missing portfolio is rendered as unconfigured. Existing snapshots without history remain readable and show an explicit history-unavailable message.
- `layer1/risk_metrics.py` calculates history snapshots. Normalization uses the preceding 52 valid metric values, skipping invalid snapshots, as selected for UI v1.1. Metric formulas for sigma, ES, and beta are unchanged.
- `layer1/layer1_vector.py` emits the histories and portfolio holding metadata from its normal entry point. Portfolio history continues to use portfolio returns, not weighted individual risk metrics.
- `docs/rve-ui-v1.1-spec.md` records the UI contract; `docs/rve-v1.0-spec.md` clarifies the selected valid-history behavior.

## Automated checks

Executed in the PR worktree on the current uncommitted change set:

| Command | Result |
|---|---|
| `PATH=/tmp/rve-layer1-ubuntu-venv/bin:$PATH PYTHONPYCACHEPREFIX=/tmp/rve-layer1-pycache python -m unittest discover -s tests -v` | 75 tests passed |
| `node --test tests/test_ui_preview.js` | 11 tests passed |
| `PYTHONPYCACHEPREFIX=/tmp/rve-layer1-pycache /tmp/rve-layer1-ubuntu-venv/bin/python -m py_compile layer1/layer1_vector.py layer1/portfolio.py layer1/risk_metrics.py tests/test_layer1_pipeline.py tests/test_portfolio.py tests/test_risk_metrics.py` | Passed |
| `git diff --check` | Passed |

The Python suite includes deterministic synthetic data tests for history output, normalization after invalid weeks, portfolio aggregation, and the JSON-producing entry point. The Node suite checks all-positive and all-negative beta sets, mixed signs, zero, clipping, unavailable beta values, risk labels and units, missing history, distinct portfolio states, and loading the checked-in calculation JSON. Synthetic UI inputs are test-only and are not used as production page data.

## Checked-in calculation snapshot

`data/layer1/7203.T_risk_vector.json` contains a computed latest snapshot and is loaded by the UI test. It predates the new history fields. The repository has no daily price history in `data/processed/` (`.gitkeep` only), so a new history-bearing market-data snapshot could not be generated without obtaining source data. The UI therefore displays the existing latest measurements and explicitly reports that historical series are unavailable. This check is not a fresh market-data calculation or a validation of real-market history.

## Browser and screenshot status

Real-browser verification and screenshots were not completed. No system Chromium, Chrome, or Firefox executable was found. A cached Playwright Chromium executable exists at `/tmp/rve-playwright-browsers/chromium_headless_shell-1248/chrome-headless-shell-linux-arm64/chrome-headless-shell`, but it cannot start because `libnspr4.so` is unavailable; the Node Playwright module is also unavailable. No system packages were installed and no screenshot is claimed. Desktop/mobile layout, browser console behavior, real browser rendering, and the synthetic-data page rendering remain to be checked in an environment with a working browser.

## Remaining verification

1. Run the page with the regenerated history-bearing output from `python layer1/layer1_vector.py` after five-year daily source histories are available.
2. Open the generated page in a browser at desktop and narrow widths; exercise the individual and portfolio tabs, missing-history state, and test-only fixtures for positive/negative/zero/clipped/null beta.
3. Save screenshots and browser console/network results, then attach the evidence to this report.
