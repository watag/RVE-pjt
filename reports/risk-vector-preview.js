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
    { key: "sigma", label: "σ 年率", unit: "%", window: 52, detail: "週次標本標準偏差 × √52" },
    { key: "ES", label: "ES 95%", unit: "%", window: 156, detail: "損失上位8週の符号付き平均" },
  ];
  const BETA_DISPLAY_LIMIT = 3.0;
  const LABELS = {
    ok: "計算済み",
    insufficient_history: "履歴不足",
    missing_price: "価格欠損",
    missing_fx: "為替欠損",
    invalid_price: "無効価格",
    zero_variance: "アンカー分散ゼロ",
    iqr_below_threshold: "IQR閾値以下",
    configuration_error: "設定不足",
    calculation_error: "計算エラー",
    not_configured: "未設定",
  };

  function statusLabel(status) {
    return LABELS[status] || status || "状態不明";
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

  function buildBetaBarModel(vector, displayLimit = BETA_DISPLAY_LIMIT) {
    return BETA_AXES.map((axis) => {
      const item = vector && vector[axis.key];
      const valid = Boolean(item && item.status === "ok" && Number.isFinite(item.value));
      const value = valid ? item.value : null;
      const magnitude = valid ? Math.min(Math.abs(value) / displayLimit, 1) * 50 : 0;
      return {
        ...axis,
        value,
        status: valueStatus(item),
        observation_count: item && Number.isInteger(item.observation_count)
          ? item.observation_count : null,
        window_weeks: item && Number.isInteger(item.window_weeks)
          ? item.window_weeks : 52,
        clipped: valid && Math.abs(value) > displayLimit,
        left: value !== null && value < 0 ? 50 - magnitude : 50,
        width: magnitude,
        zero: valid && value === 0,
      };
    });
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function observationText(item, fallbackWindow) {
    const windowWeeks = Number.isInteger(item && item.window_weeks)
      ? item.window_weeks : fallbackWindow;
    const count = Number.isInteger(item && item.observation_count)
      ? item.observation_count : "不明";
    return `対象 ${windowWeeks}週 · 有効観測 ${count}`;
  }

  function renderRiskLevels(vector) {
    return `<section class="risk-level"><h3>リスク水準</h3><div class="stats">`
      + RISK_METRICS.map((metric) => {
        const item = vector && vector[metric.key];
        const valid = item && item.status === "ok" && Number.isFinite(item.value);
        const status = valid ? "計算済み" : statusLabel(valueStatus(item));
        return `<article class="stat"><div class="label">${metric.label}</div>`
          + `<div class="value">${valid ? formatValue(metric.key, item.value) : "未算出"}</div>`
          + `<div class="detail">${metric.unit} · ${metric.detail}</div>`
          + `<div class="detail">${escapeHtml(status)} · ${escapeHtml(observationText(item, metric.window))}</div>`
          + `</article>`;
      }).join("")
      + `</div></section>`;
  }

  function renderBetaBars(vector) {
    const model = buildBetaBarModel(vector);
    return `<section class="sensitivity"><h3>アンカー感応度 <span class="muted">実測β</span></h3>`
      + `<p class="detail">β=0を中央に表示。青は正、赤は負です。表示範囲は −3.0〜+3.0。範囲外はクリップし、実測値を併記します。</p>`
      + `<div class="beta-axis"><span>−3</span><span>β=0</span><span>+3</span></div>`
      + model.map((axis) => {
        const valid = axis.value !== null;
        const formatted = valid ? formatValue(axis.key, axis.value) : "未算出";
        const tooltip = `${axis.label} (${axis.ticker}): β ${formatted}; ${observationText(axis, 52)}; ${statusLabel(axis.status)}`;
        const fill = valid && !axis.zero
          ? `<span class="beta-fill ${axis.value < 0 ? "negative" : "positive"}" style="left:${axis.left}%;width:${axis.width}%"></span>`
          : "";
        const zero = axis.zero ? `<span class="beta-zero" aria-label="βゼロ"></span>` : "";
        const clipText = axis.clipped ? `<span class="clip-label">表示範囲超過</span>` : "";
        const detail = valid
          ? `${escapeHtml(observationText(axis, 52))}${axis.clipped ? " · 表示範囲超過" : ""}`
          : statusLabel(axis.status);
        return `<div class="beta-row" title="${escapeHtml(tooltip)}">`
          + `<div class="beta-label">${axis.label}<small>${axis.ticker}</small></div>`
          + `<div class="beta-track">${fill}${zero}</div>`
          + `<div class="beta-number">${valid ? formatted : escapeHtml(statusLabel(axis.status))}${clipText}</div>`
          + `<div class="beta-detail">${escapeHtml(detail)}</div></div>`;
      }).join("")
      + `</section>`;
  }

  function renderNormalizationDetails(vector) {
    const metrics = [...RISK_METRICS.map((metric) => metric.key), ...BETA_AXES.map((axis) => axis.key)];
    const rows = metrics.map((key) => {
      const item = vector && vector[key];
      const normalized = item && item.normalized;
      const status = item && item.normalization_status;
      const value = status === "ok" && Number.isFinite(normalized)
        ? `${normalized > 0 ? "+" : ""}${normalized.toFixed(2)}`
        : status === "ok" ? "正規化値なし" : statusLabel(status);
      return `<li><span>${escapeHtml(key)}</span>: ${escapeHtml(value)}</li>`;
    }).join("");
    return `<details class="normalization"><summary>過去分布に対する相対位置（補助情報）</summary>`
      + `<p class="detail">各指標の生値を、その銘柄自身の直前52週の中央値・IQRと比較した値です。βの感応度や銘柄間の絶対リスクを表しません。</p>`
      + `<ul>${rows}</ul></details>`;
  }

  function renderVector(vector) {
    if (!vector || typeof vector !== "object") {
      return `<div class="notice">計算結果がありません。</div>`;
    }
    return renderRiskLevels(vector) + renderBetaBars(vector) + renderNormalizationDetails(vector);
  }

  function portfolioMessage(snapshot) {
    const status = snapshot && snapshot.portfolio_status;
    const reason = snapshot && snapshot.portfolio_reason;
    if (status === "not_configured") return "ポートフォリオ未設定: ウェイト履歴または現在ウェイトがありません。";
    if (!snapshot || !snapshot.portfolio) {
      return `${statusLabel(status)}${reason ? `: ${reason}` : ""}`;
    }
    return "";
  }

  function renderPortfolio(snapshot) {
    const message = portfolioMessage(snapshot);
    if (message) return `<div class="notice">${escapeHtml(message)}</div>`;
    const vector = snapshot.portfolio;
    const mode = vector.analysis_mode || snapshot.portfolio_mode;
    const modeLabel = mode === "scenario"
      ? "シナリオ分析（現在ウェイトを過去へ適用）"
      : mode === "realized" ? "実績分析（当週の期初ウェイト）" : "分析モード未設定";
    const diagnostics = vector.portfolio_diagnostics;
    const issues = diagnostics && Array.isArray(diagnostics.issues) ? diagnostics.issues : [];
    const issueSummary = diagnostics && diagnostics.invalid_weeks
      ? `<p class="notice">計算不能週 ${diagnostics.invalid_weeks} / 有効週 ${diagnostics.valid_weeks}<br>`
        + issues.map((issue) => `${escapeHtml(issue.week_ending)}: ${escapeHtml(statusLabel(issue.status))} (${escapeHtml(issue.reason)})`).join("<br>")
        + `</p>`
      : "";
    return `<p class="badge">${escapeHtml(modeLabel)}</p>${issueSummary}${renderVector(vector)}`;
  }

  function displaySnapshot(doc, snapshot) {
    doc.querySelector("#status").textContent = "計算データを読み込みました";
    doc.querySelector("#status").classList.remove("error");
    doc.querySelector("#asof").textContent = snapshot.asset && snapshot.asset.as_of
      ? `基準週 ${snapshot.asset.as_of}` : "基準週 未算出";
    doc.querySelector("#asset-symbol").textContent = snapshot.asset_symbol || "";
    doc.querySelector("#portfolio-mode").textContent = "";
    doc.querySelector("#asset").innerHTML = renderVector(snapshot.asset);
    doc.querySelector("#portfolio").innerHTML = renderPortfolio(snapshot);
    const generatedAt = snapshot.generated_at ? new Date(snapshot.generated_at) : null;
    const generatedText = generatedAt && Number.isFinite(generatedAt.getTime())
      ? `生成 ${generatedAt.toLocaleString("ja-JP")} · ${Math.max(0, Math.floor((Date.now() - generatedAt.getTime()) / 86400000))}日前`
      : "生成時刻なし";
    const priceText = Object.entries(snapshot.price_fields || {})
      .map(([symbol, field]) => `${symbol}=${field}`).join(" · ");
    doc.querySelector("#sources").textContent = `${generatedText} · 価格系列: ${priceText}`
      + ` · FX: ${snapshot.fx_alignment || "未設定"}`;
  }

  async function loadSnapshot(doc, fetcher) {
    try {
      const response = await fetcher("../data/layer1/7203.T_risk_vector.json", { cache: "no-store" });
      if (!response.ok) throw new Error("計算結果JSONがありません");
      const snapshot = await response.json();
      if (!snapshot || typeof snapshot !== "object" || !snapshot.asset || typeof snapshot.asset !== "object") {
        throw new Error("計算結果JSONの形式が不正です");
      }
      displaySnapshot(doc, snapshot);
    } catch (error) {
      doc.querySelector("#status").textContent = "計算結果なし";
      doc.querySelector("#status").classList.add("error");
      doc.querySelector("#asset").textContent = `${error.message}: ../data/layer1/7203.T_risk_vector.json`;
      doc.querySelector("#portfolio").textContent = "ポートフォリオ結果は未表示です。";
    }
  }

  const api = {
    BETA_AXES,
    BETA_DISPLAY_LIMIT,
    buildBetaBarModel,
    formatValue,
    portfolioMessage,
    renderVector,
    renderPortfolio,
    loadSnapshot,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root.document) loadSnapshot(root.document, root.fetch.bind(root));
})(globalThis);
