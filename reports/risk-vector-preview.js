(function (root) {
  "use strict";

  const BETA_AXES = [
    { key: "beta_gold", label: "Gold", ticker: "1540.T" },
    { key: "beta_us_equity", label: "US Equity", ticker: "^GSPC" },
    { key: "beta_japan_equity", label: "Japan Equity", ticker: "1306.T" },
    { key: "beta_us_treasury", label: "US Treasury", ticker: "TLT" },
    { key: "beta_japan_bond", label: "Japan Bond", ticker: "2510.T" },
  ];
  const RISK_METRICS = [
    { key: "sigma", label: "年率変動性（σ）", unit: "%", window: 52, detail: "週次標本標準偏差 × √52" },
    { key: "ES", label: "ES 95%（損失上位8週の平均）", unit: "%", window: 156, detail: "直近156週の符号付き平均" },
  ];
  const NORMALIZED_METRICS = [
    ...RISK_METRICS.map(({ key, label }) => ({ key, label })),
    ...BETA_AXES.map(({ key, label }) => ({ key, label: `${label} β` })),
  ];
  const BETA_LIMIT = 3;
  const STATUS_LABELS = {
    ok: "算出済み",
    insufficient_history: "履歴不足",
    missing_price: "価格欠損",
    missing_fx: "為替欠損",
    invalid_price: "無効価格",
    zero_variance: "アンカー分散ゼロ",
    iqr_below_threshold: "IQR閾値以下",
    configuration_error: "設定エラー",
    calculation_error: "計算エラー",
    not_configured: "未設定",
  };

  function statusLabel(status) {
    return STATUS_LABELS[status] || status || "状態不明";
  }

  function valueStatus(item) {
    return item && item.status === "ok" && !Number.isFinite(item.value)
      ? "calculation_error" : item && item.status;
  }

  function formatValue(metric, value) {
    if (!Number.isFinite(value)) return "未算出";
    if (metric === "sigma" || metric === "ES") return `${(value * 100).toFixed(2)}%`;
    return `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function observationText(item, defaultWindow = 52) {
    const windowWeeks = Number.isInteger(item && item.window_weeks)
      ? item.window_weeks : defaultWindow;
    const count = Number.isInteger(item && item.observation_count)
      ? item.observation_count : "不明";
    return `対象${windowWeeks}週・有効観測${count}`;
  }

  function buildRadarModel(vector, radius = 108) {
    const cx = 180;
    const cy = 146;
    const axes = BETA_AXES.map((axis, index) => {
      const item = vector && vector[axis.key];
      const valid = Boolean(item && item.status === "ok" && Number.isFinite(item.value));
      const value = valid ? item.value : null;
      const clippedValue = valid ? Math.max(-BETA_LIMIT, Math.min(BETA_LIMIT, value)) : null;
      const pointRadius = valid ? radius * (clippedValue + BETA_LIMIT) / (2 * BETA_LIMIT) : null;
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / BETA_AXES.length;
      return {
        ...axis,
        value,
        status: valueStatus(item),
        window_weeks: item && Number.isInteger(item.window_weeks) ? item.window_weeks : 52,
        observation_count: item && Number.isInteger(item.observation_count) ? item.observation_count : null,
        clipped: valid && value !== clippedValue,
        point: valid ? { x: cx + pointRadius * Math.cos(angle), y: cy + pointRadius * Math.sin(angle) } : null,
        angle,
      };
    });
    const segments = [];
    axes.forEach((axis, index) => {
      const next = axes[(index + 1) % axes.length];
      if (axis.point && next.point) segments.push([axis.point, next.point]);
    });
    return { axes, segments, polygon: axes.every((axis) => axis.point) ? axes.map((axis) => axis.point) : null, cx, cy, radius };
  }

  function radarSvg(vector) {
    const model = buildRadarModel(vector);
    const { cx, cy, radius } = model;
    const ring = (fraction, cls) => {
      const points = BETA_AXES.map((_, index) => {
        const angle = -Math.PI / 2 + (2 * Math.PI * index) / BETA_AXES.length;
        return `${cx + radius * fraction * Math.cos(angle)},${cy + radius * fraction * Math.sin(angle)}`;
      }).join(" ");
      return `<polygon class="radar-ring ${cls}" points="${points}"/>`;
    };
    const spokes = BETA_AXES.map((axis, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / BETA_AXES.length;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      const lx = cx + (radius + 29) * Math.cos(angle);
      const ly = cy + (radius + 29) * Math.sin(angle);
      const anchor = Math.abs(lx - cx) < 10 ? "middle" : lx < cx ? "end" : "start";
      return `<line class="radar-spoke" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>`
        + `<text class="radar-label" x="${lx}" y="${ly}" text-anchor="${anchor}">`
        + `<tspan>${axis.label}</tspan><tspan class="radar-ticker" x="${lx}" dy="13">${axis.ticker}</tspan></text>`;
    }).join("");
    const segments = model.segments.map(([a, b]) =>
      `<line class="radar-segment" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`
    ).join("");
    const polygon = model.polygon
      ? `<polygon class="radar-area" points="${model.polygon.map((p) => `${p.x},${p.y}`).join(" ")}"/>`
      : "";
    const markers = model.axes.map((axis) => {
      if (!axis.point) return "";
      const sign = axis.value > 0 ? "positive" : axis.value < 0 ? "negative" : "zero";
      const clipped = axis.clipped ? " · 表示範囲超過" : "";
      return `<circle class="radar-point ${sign}" cx="${axis.point.x}" cy="${axis.point.y}" r="5">`
        + `<title>${axis.label} ${axis.ticker}: β ${formatValue(axis.key, axis.value)}${clipped}</title></circle>`;
    }).join("");
    const labels = `<text class="radar-tick tick-center" x="${cx}" y="${cy + 4}">−3</text>`
      + `<text class="radar-tick" x="${cx + 4}" y="${cy - radius / 2 + 4}">0</text>`
      + `<text class="radar-tick" x="${cx + 4}" y="${cy - radius + 4}">+3</text>`;
    return `<svg class="radar" viewBox="0 0 360 330" role="img" aria-label="アンカー実測βレーダー">`
      + `<title>βの符号付きレーダー。中心は−3、破線リングは0、外周は+3。</title>`
      + `${ring(1, "outer-ring")}${ring(0.5, "zero-ring")}${spokes}${labels}${polygon}${segments}${markers}</svg>`;
  }

  function renderBetaSensitivity(vector) {
    const model = buildRadarModel(vector);
    const rows = model.axes.map((axis) => {
      const valid = axis.point !== null;
      const value = valid ? formatValue(axis.key, axis.value) : "未算出";
      const clip = axis.clipped ? `<strong class="clip-state">範囲超過</strong>` : "";
      const status = valid ? "算出済み" : statusLabel(axis.status);
      return `<tr><th>${axis.label}<small>${axis.ticker}</small></th>`
        + `<td class="number">${valid ? value : escapeHtml(status)} ${clip}</td>`
        + `<td>${escapeHtml(observationText(axis))} · ${escapeHtml(status)}</td></tr>`;
    }).join("");
    const anyPoint = model.axes.some((axis) => axis.point);
    return `<div class="sensitivity-layout">${anyPoint ? radarSvg(vector) : `<div class="notice">βを算出できるアンカーがありません。</div>`}`
      + `<div class="beta-legend"><b>実測β</b> · 正は外向き、負は内向き。ゼロリングがβ=0、中心はβ=0ではありません。レーダー面積は総合リスクスコアではありません。</div></div>`
      + `<div class="table-scroll"><table class="beta-table"><thead><tr><th>アンカー</th><th>実測β</th><th>状態・推定期間・観測数</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function renderRiskCards(vector) {
    return `<div class="stats">${RISK_METRICS.map((metric) => {
      const item = vector && vector[metric.key];
      const valid = item && item.status === "ok" && Number.isFinite(item.value);
      const status = valid ? "算出済み" : statusLabel(valueStatus(item));
      return `<article class="stat"><h3>${metric.label}</h3>`
        + `<div class="value">${valid ? formatValue(metric.key, item.value) : "未算出"}</div>`
        + `<div class="detail">${metric.detail} · ${metric.unit}</div>`
        + `<div class="detail">${escapeHtml(observationText(item, metric.window))} · ${escapeHtml(status)}</div></article>`;
    }).join("")}</div>`;
  }

  function metricForSeries(point, key, field) {
    const item = point && point[key];
    if (!item) return { value: null, status: "missing_price" };
    const status = field === "normalized" ? item.normalization_status : item.status;
    const valid = status === "ok" && Number.isFinite(item[field]);
    return { value: valid ? item[field] : null, status, rawStatus: item.status };
  }

  function buildLineModel(history, key, field) {
    const points = (Array.isArray(history) ? history : []).map((snapshot, index, all) => {
      const result = metricForSeries(snapshot, key, field);
      const maxAbs = 0;
      return { index, asOf: snapshot.as_of, ...result, maxAbs };
    });
    const valid = points.filter((point) => Number.isFinite(point.value));
    const extent = Math.max(1e-12, ...valid.map((point) => Math.abs(point.value)));
    const width = 640;
    const height = 170;
    const left = 42;
    const right = 12;
    const top = 14;
    const bottom = 25;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const mapped = points.map((point) => ({
      ...point,
      x: points.length > 1 ? left + (point.index / (points.length - 1)) * plotWidth : left + plotWidth / 2,
      y: top + (1 - (Number.isFinite(point.value) ? point.value / extent : 0)) * plotHeight / 2,
    }));
    const segments = [];
    for (let index = 0; index + 1 < mapped.length; index += 1) {
      if (Number.isFinite(mapped[index].value) && Number.isFinite(mapped[index + 1].value)) {
        segments.push([mapped[index], mapped[index + 1]]);
      }
    }
    return { points: mapped, segments, extent, width, height, left, right, top, bottom, plotHeight };
  }

  function renderLineChart(history, metric, field) {
    if (!Array.isArray(history) || history.length === 0) {
      return `<div class="notice">履歴データがありません。</div>`;
    }
    const model = buildLineModel(history, metric.key, field);
    const zeroY = model.top + model.plotHeight / 2;
    const lines = model.segments.map(([a, b]) =>
      `<line class="series-line ${field === "value" ? "raw-beta-line" : "normalized-line"}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`
    ).join("");
    const dots = model.points.filter((point) => Number.isFinite(point.value)).map((point) => {
      const item = history[point.index][metric.key];
      const text = `${point.asOf}: ${formatValue(metric.key, point.value)} · ${statusLabel(point.status)} · ${observationText(item, metric.key === "ES" ? 156 : 52)}`;
      return `<circle class="series-point" cx="${point.x}" cy="${point.y}" r="2.6"><title>${escapeHtml(text)}</title></circle>`;
    }).join("");
    const firstDate = history[0] && history[0].as_of ? String(history[0].as_of).slice(0, 10) : "";
    const lastDate = history[history.length - 1] && history[history.length - 1].as_of
      ? String(history[history.length - 1].as_of).slice(0, 10) : "";
    const latestSnapshot = history[history.length - 1];
    const latestMetric = latestSnapshot && latestSnapshot[metric.key];
    const latestPoint = model.points[model.points.length - 1];
    const seriesName = field === "normalized" ? "過去分布に対する相対位置 z" : "実測β";
    return `<svg class="trend-chart" viewBox="0 0 ${model.width} ${model.height}" role="img" aria-label="${escapeHtml(metric.label)} ${seriesName}の直近52週推移">`
      + `<line class="zero-line" x1="${model.left}" y1="${zeroY}" x2="${model.width - model.right}" y2="${zeroY}"/>`
      + `<text class="chart-scale" x="2" y="${model.top + 4}">+${model.extent.toPrecision(2)}</text>`
      + `<text class="chart-scale" x="2" y="${zeroY + 4}">0</text>`
      + `<text class="chart-scale" x="2" y="${model.height - model.bottom}">−${model.extent.toPrecision(2)}</text>`
      + `${lines}${dots}<text class="chart-date" x="${model.left}" y="${model.height - 4}">${escapeHtml(firstDate)}</text>`
      + `<text class="chart-date" x="${model.width - model.right}" y="${model.height - 4}" text-anchor="end">${escapeHtml(lastDate)}</text></svg>`
      + `<p class="detail">${seriesName} · 最新 ${escapeHtml(lastDate || "基準日不明")} · 状態 ${escapeHtml(statusLabel(latestPoint && latestPoint.status))} · ${escapeHtml(observationText(latestMetric, metric.key === "ES" ? 156 : 52))} · このグラフ内で自動調整した目盛りです。欠損週は線をつなぎません。</p>`;
  }

  function renderTrendCards(history, field, metrics) {
    return `<div class="trend-grid">${metrics.map((metric) =>
      `<article class="trend-card"><h4>${escapeHtml(metric.label)}</h4>${renderLineChart(history, metric, field)}</article>`
    ).join("")}</div>`;
  }

  function renderNormalizationHistory(history) {
    return `<section><h3>正規化7指標</h3><p class="detail">対象週より前の有効な指標値52個を基準にしたz値。0は過去分布の中央値です。指標・銘柄をまたぐ絶対値比較には使えません。</p>`
      + renderTrendCards(history, "normalized", NORMALIZED_METRICS) + `</section>`;
  }

  function renderBetaHistory(history) {
    return `<section><h3>実測βの推移</h3><p class="detail">正規化βとは別表示です。縦軸は各アンカーの実測βで、欠損週は線をつなぎません。</p>`
      + renderTrendCards(history, "value", BETA_AXES) + `</section>`;
  }

  function portfolioMessage(snapshot) {
    const status = snapshot && snapshot.portfolio_status;
    const reason = snapshot && snapshot.portfolio_reason;
    if (status === "not_configured") return "ポートフォリオ未設定: ウェイト履歴または現在ウェイトがありません。";
    if (!snapshot || !snapshot.portfolio) return `${statusLabel(status)}${reason ? `: ${reason}` : ""}`;
    if (!snapshot.portfolio.sigma) {
      const detail = snapshot.portfolio.reason || reason;
      return `${statusLabel(snapshot.portfolio.status || status)}${detail ? `: ${detail}` : ""}`;
    }
    return "";
  }

  function renderHoldings(holdings) {
    if (!holdings || !holdings.weights || !Object.keys(holdings.weights).length) {
      return `<p class="notice">表示できる構成銘柄・ウェイトがありません。</p>`;
    }
    const rows = Object.entries(holdings.weights).map(([symbol, weight]) =>
      `<li>${escapeHtml(symbol)}: ${Number.isFinite(weight) ? `${(weight * 100).toFixed(2)}%` : "無効値"}</li>`
    ).join("");
    const date = holdings.as_of ? `基準週 ${escapeHtml(holdings.as_of)}` : "現在ウェイト";
    return `<section class="holdings"><h3>構成銘柄・ウェイト</h3><p class="detail">${date}</p><ul>${rows}</ul></section>`;
  }

  function renderPortfolioPage(snapshot) {
    const message = portfolioMessage(snapshot);
    if (message) return `<div class="notice">${escapeHtml(message)}</div>`;
    const vector = snapshot.portfolio;
    const mode = vector.analysis_mode || snapshot.portfolio_mode;
    const modeLabel = mode === "scenario"
      ? "シナリオ分析（現在ウェイトを過去に適用）"
      : mode === "realized" ? "実績分析（週ごとの期初ウェイト）" : "分析モード未設定";
    const diagnostics = vector.portfolio_diagnostics;
    const issues = diagnostics && Array.isArray(diagnostics.issues) ? diagnostics.issues : [];
    const diagnosticsHtml = diagnostics && diagnostics.invalid_weeks
      ? `<div class="notice">無効週 ${diagnostics.invalid_weeks} / 有効週 ${diagnostics.valid_weeks}<br>`
        + issues.map((issue) => `${escapeHtml(issue.week_ending)}: ${escapeHtml(statusLabel(issue.status))} (${escapeHtml(issue.reason)})`).join("<br>")
        + `</div>` : "";
    return `<p class="badge">${escapeHtml(modeLabel)}</p>${renderHoldings(snapshot.portfolio_holdings)}`
      + `${diagnosticsHtml}<section class="card-inner"><h3>アンカー感応度</h3>${renderBetaSensitivity(vector)}</section>`
      + `<section class="card-inner"><h3>リスク水準</h3>${renderRiskCards(vector)}</section>`
      + `<section class="card-inner"><h3>過去推移</h3>${renderNormalizationHistory(snapshot.portfolio_history)}${renderBetaHistory(snapshot.portfolio_history)}</section>`;
  }

  function renderAssetPage(snapshot) {
    const vector = snapshot.asset;
    return `<section class="card-inner"><h2>アンカー感応度</h2>${renderBetaSensitivity(vector)}</section>`
      + `<section class="card-inner"><h2>リスク水準</h2>${renderRiskCards(vector)}</section>`
      + `<section class="card-inner"><h2>過去の相対的位置と変化</h2>${renderNormalizationHistory(snapshot.asset_history)}${renderBetaHistory(snapshot.asset_history)}</section>`;
  }

  function setActiveTab(doc, tabName) {
    const individual = tabName === "individual";
    doc.querySelector("#individual-tab").setAttribute("aria-selected", String(individual));
    doc.querySelector("#portfolio-tab").setAttribute("aria-selected", String(!individual));
    doc.querySelector("#individual-page").hidden = !individual;
    doc.querySelector("#portfolio-page").hidden = individual;
  }

  function bindTabs(doc) {
    doc.querySelector("#individual-tab").addEventListener("click", () => setActiveTab(doc, "individual"));
    doc.querySelector("#portfolio-tab").addEventListener("click", () => setActiveTab(doc, "portfolio"));
  }

  function displaySnapshot(doc, snapshot) {
    doc.querySelector("#status").textContent = "計算データを読み込みました";
    doc.querySelector("#status").classList.remove("error");
    doc.querySelector("#asof").textContent = snapshot.asset && snapshot.asset.as_of
      ? `基準日 ${String(snapshot.asset.as_of).slice(0, 10)}` : "基準日 未算出";
    doc.querySelector("#asset-symbol").textContent = snapshot.asset_symbol || "";
    doc.querySelector("#individual-page").innerHTML = renderAssetPage(snapshot);
    doc.querySelector("#portfolio-page").innerHTML = renderPortfolioPage(snapshot);
    const generatedAt = snapshot.generated_at ? new Date(snapshot.generated_at) : null;
    const generatedText = generatedAt && Number.isFinite(generatedAt.getTime())
      ? `生成 ${generatedAt.toLocaleString("ja-JP")} · ${Math.max(0, Math.floor((Date.now() - generatedAt.getTime()) / 86400000))}日前`
      : "生成時刻なし";
    const priceText = Object.entries(snapshot.price_fields || {})
      .map(([symbol, field]) => `${symbol}=${field}`).join(" · ");
    doc.querySelector("#sources").textContent = `${generatedText} · 価格系列: ${priceText}`
      + ` · FX: ${snapshot.fx_alignment || "未設定"}`;
    setActiveTab(doc, "individual");
  }

  async function loadSnapshot(doc, fetcher) {
    try {
      const response = await fetcher("../data/layer1/7203.T_risk_vector.json", { cache: "no-store" });
      if (!response.ok) throw new Error("計算結果JSONがありません");
      const snapshot = await response.json();
      if (!snapshot || typeof snapshot !== "object" || !snapshot.asset) {
        throw new Error("計算結果JSONの形式が不正です（個別銘柄データがありません）");
      }
      displaySnapshot(doc, snapshot);
    } catch (error) {
      doc.querySelector("#status").textContent = "計算結果なし";
      doc.querySelector("#status").classList.add("error");
      doc.querySelector("#individual-page").textContent = `${error.message}: ../data/layer1/7203.T_risk_vector.json`;
      doc.querySelector("#portfolio-page").textContent = "ポートフォリオ結果は未表示です。";
    }
  }

  const api = {
    BETA_AXES,
    BETA_LIMIT,
    buildRadarModel,
    buildLineModel,
    formatValue,
    renderBetaSensitivity,
    renderRiskCards,
    renderLineChart,
    renderNormalizationHistory,
    renderBetaHistory,
    renderPortfolioPage,
    renderAssetPage,
    portfolioMessage,
    displaySnapshot,
    loadSnapshot,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root.document) {
    bindTabs(root.document);
    loadSnapshot(root.document, root.fetch.bind(root));
  }
})(globalThis);
