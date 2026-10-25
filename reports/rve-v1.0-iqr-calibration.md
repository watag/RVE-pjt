# RVE v1.0 IQR threshold calibration

## Decision and interpretation

The configuration stores one minimum IQR per metric. Each threshold has the
same units as that metric's raw historical series: annualized decimal return
for `sigma`, weekly decimal loss for `ES`, and dimensionless units for each
beta. Normalization returns null with `iqr_below_threshold` when the prior
52-value IQR is less than or equal to the configured threshold. Missing or
invalid threshold settings continue to return `configuration_error`.

The selected calibration rule is the 5th percentile, using NumPy's `linear`
quantile method, of strictly positive IQRs observed in rolling prior-52-metric-
value windows. The current metric observation must be valid but is excluded
from its IQR window. The calibration pool contains the configured asset
`7203.T` and the five RVE anchors. For each beta metric, an anchor's beta to
itself is excluded because it is identically one and would reduce the IQR floor
to floating-point noise. This rule is configured with the same quantile for
all metrics; the resulting numeric thresholds differ by metric and units.

## Data snapshot

- Source: Yahoo Finance, downloaded with `yfinance 1.2.0`, `auto_adjust=False`.
- Downloaded: 2026-10-25 UTC.
- Data span: daily history 2021-10-25 through 2026-10-23; 261 W-FRI buckets
  from 2021-10-29 through 2026-10-23.
- Python used for calibration: 3.12; NumPy 2.4.3, pandas 3.0.1, PyYAML 6.0.3
  (the versions pinned for RVE Core CI).
- Selected fields: `Adj Close` for `7203.T`, `1540.T`, `1306.T`, `TLT`, and
  `2510.T`; `Close` for `^GSPC`; `Close` for `JPY=X`.
- Yahoo's `JPY=X` quote was labelled USD/JPY; observed values ranged from
  112.8820 to 163.8640, with median 147.3805, consistent with JPY per USD.
- Exact same-calendar-date matching found one absent FX row (2025-04-21) in
  each USD asset's daily date set. No FX value was carried forward. The missing
  row was not a selected weekly final price; all six instrument series had 260
  valid weekly returns, with the first week reserved for return warm-up.
- The downloaded price files remain in a temporary directory and are not
  committed. The result is therefore an empirical calibration snapshot, not a
  frozen vendor dataset. Yahoo may revise historical values.

## Calibrated thresholds

| Metric | Threshold | Unit | Positive historical IQR samples |
|---|---:|---|---:|
| `sigma` | 0.0024348584456083725 | Annualized decimal return | 942 |
| `ES` | 0.0003297047452374517 | Weekly decimal loss | 318 |
| `beta_gold` | 0.010262296851308451 | Beta units | 785 |
| `beta_us_equity` | 0.016443156549517023 | Beta units | 785 |
| `beta_japan_equity` | 0.019550831087507322 | Beta units | 785 |
| `beta_us_treasury` | 0.021453844888890378 | Beta units | 785 |
| `beta_japan_bond` | 0.20850612100366078 | Beta units | 785 |

These values are tied to the six configured instruments and this five-year
sample. They should be recalibrated if the configured universe or data source
changes materially. In particular, there is only one individual equity in the
calibration pool; this does not establish that the same floors are appropriate
for every future security.

## Reproduction

From the repository root, using the pinned requirements:

```sh
python fetch/fetch_csv.py
python scripts/calibrate_iqr_thresholds.py \
  --data-dir data/processed \
  --output /tmp/rve-iqr-calibration.json
```

The first command needs Yahoo Finance network access. The calibration CLI reads
the retained configured price histories and does not download or modify them.
It fails on invalid/non-positive prices, duplicate or invalid dates, missing
anchors, or unavailable positive-IQR samples. The checked-in offline tests use
synthetic data; they do not contact Yahoo Finance.
