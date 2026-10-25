(function (root) {
  "use strict";

  const AXES = [
    { key: "sigma", label: "σ 年率", kind: "return" },
    { key: "ES", label: "ES 95%", kind: "return" },
    { key: "beta_gold", label: "Gold β", kind: "beta" },
    { key: "beta_us_equity", label: "US Equity β", kind: "beta" },
    { key: "beta_japan_equity", label: "Japan Equity β", kind: "beta" },
    { key: "beta_us_treasury", label: "US Treasury β", kind: "beta" },
    { key: "beta_japan_bond", label: "Japan Bond β", kind: "beta" },
  ];
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
    partial_or_invalid_history: "一部の週を計算できません",
  };

  function statusLabel(status) {
    return LABELS[status] || status || "状態不明";
  }

  function formatValue(metric, value) {
    if (!Number.isFinite(value)) return "未算出";
    const axis = AXES.find((item) => item.key === metric);
    if (axis && axis.kind === "return") return `${(value * 100).toFixed(2)}%`;
    return value.toFixed(3);
  }

  function buildRadarModel(vector) {
    const raw = AXES.map((axis) => {
      const item = vector && vector[axis.key];
      const value = item && item.normalized;
      return Number.isFinite(value) && item.normalization_status === "ok"
        ? value
        : null;
    });
    const scale = Math.max(1, ...raw.filter(Number.isFinite).map(Math.abs));
    const points = raw.map((value, index) => {
      if (value === null) return null;
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / AXES.length;
      // Signed z-scores use the middle ring as zero; negative values move inward.
      const radius = 120 * (value / scale + 1) / 2;
      return {
        x: 180 + radius * Math.cos(angle),
        y: 165 + radius * Math.sin(angle),
      };
    });
    const segments = [];
    for (let index = 0; index < points.length; index += 1) {
      const next = (index + 1) % points.length;
      if (points[index] && points[next]) {
        segments.push([points[index], points[next]]);
      }
    }
    return { axes: AXES, raw, points, segments, scale };
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function metricCards(vector) {
    return `<div class="stats">${AXES.map((axis) => {
      const item = vector && vector[axis.key];
      const value = item && item.value;
      const normalized = item && item.normalized;
      const reason = statusLabel(item && item.status);
      const normReason = statusLabel(item && item.normalization_status);
      return `<div class="stat"><div class="label">${axis.label}</div>`
        + `<div class="value">${formatValue(axis.key, value)}</div>`
        + `<div class="detail">${escapeHtml(reason)} · 正規化 `
        + `${Number.isFinite(normalized) ? normalized.toFixed(2) : escapeHtml(normReason)}</div></div>`;
    }).join("")}</div>`;
  }

  function radarSvg(vector) {
    const model = buildRadarModel(vector);
    const cx = 180;
    const cy = 165;
    const outer = 120;
    const grid = [0.25, 0.5, 0.75, 1].map((fraction) => {
      const points = model.axes.map((_, index) => {
        const angle = -Math.PI / 2 + (2 * Math.PI * index) / model.axes.length;
        return `${cx + outer * fraction * Math.cos(angle)},${cy + outer * fraction * Math.sin(angle)}`;
      }).join(" ");
      return `<polygon class="radar-grid" fill="none" stroke="#344354" points="${points}"></polygon>`;
    }).join("");
    const spokes = model.axes.map((axis, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / model.axes.length;
      const x = cx + outer * Math.cos(angle);
      const y = cy + outer * Math.sin(angle);
      const lx = cx + (outer + 31) * Math.cos(angle);
      const ly = cy + (outer + 31) * Math.sin(angle);
      const anchor = Math.abs(lx - cx) < 12 ? "middle" : lx < cx ? "end" : "start";
      return `<line class="radar-spoke" stroke="#48596c" x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"></line>`
        + `<text class="radar-label" fill="#edf4fb" font-size="11" x="${lx}" y="${ly}" text-anchor="${anchor}">${axis.label}</text>`;
    }).join("");
    const segments = model.segments.map(([a, b]) =>
      `<line class="radar-segment" stroke="#70b7ff" stroke-width="3" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"></line>`
    ).join("");
    const points = model.points.map((point, index) => point
      ? `<circle class="radar-point" fill="#70b7ff" stroke="#10151d" stroke-width="2" cx="${point.x}" cy="${point.y}" r="4"><title>${model.axes[index].label}: ${model.raw[index].toFixed(2)}</title></circle>`
      : "").join("");
    const zeroRing = `<polygon class="radar-zero" fill="none" stroke="#8493a4" stroke-dasharray="4 3" points="${model.axes.map((_, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / model.axes.length;
      const radius = outer / 2;
      return `${cx + radius * Math.cos(angle)},${cy + radius * Math.sin(angle)}`;
    }).join(" ")}"></polygon>`;
    const hasValues = model.points.some(Boolean);
    return `<svg class="radar" width="100%" height="330" style="height:auto;max-height:440px;display:block;margin:auto" viewBox="0 0 360 330" role="img" aria-label="正規化リスクベクトル">`
      + `<title>銘柄自身の過去52週に対する正規化リスクベクトル</title>`
      + `${grid}${zeroRing}${spokes}${segments}${points}</svg>`
      + `<p class="detail">中心側は負、中央線は0、外側は正。表示値は当該銘柄自身の履歴に対するz値です。`
      + `${hasValues ? "未算出軸は点・線を描きません。" : "正規化可能な値がないため、レーダー点はありません。"}</p>`;
  }

  function renderVector(vector) {
    if (!vector || !vector.sigma) {
      return `<div class="notice">${escapeHtml(statusLabel(vector && vector.status))}`
        + `${vector && vector.reason ? ` · ${escapeHtml(vector.reason)}` : ""}</div>`;
    }
    return radarSvg(vector) + metricCards(vector);
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
    const issueSummary = diagnostics && diagnostics.invalid_weeks
      ? `<p class="notice">計算不能週 ${diagnostics.invalid_weeks} / 有効週 ${diagnostics.valid_weeks}<br>`
        + diagnostics.issues.map((issue) => `${escapeHtml(issue.week_ending)}: ${escapeHtml(statusLabel(issue.status))} (${escapeHtml(issue.reason)})`).join("<br>")
        + `</p>`
      : "";
    return `<p class="badge">${escapeHtml(modeLabel)}</p>${issueSummary}${renderVector(vector)}`;
  }

  function displaySnapshot(doc, snapshot) {
    doc.querySelector("#status").textContent = "計算データを読み込みました";
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
      if (!snapshot || typeof snapshot !== "object" || !snapshot.asset) {
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

  const api = { AXES, buildRadarModel, formatValue, portfolioMessage, renderVector, renderPortfolio, loadSnapshot };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root.document) loadSnapshot(root.document, root.fetch.bind(root));
})(globalThis);
