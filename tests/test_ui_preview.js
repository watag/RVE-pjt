"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ui = require("../reports/risk-vector-preview.js");

function metric(value, normalized = value, status = "ok", metadata = {}) {
  return {
    value,
    normalized,
    status,
    normalization_status: normalized === null ? "configuration_error" : "ok",
    window_weeks: 52,
    observation_count: 52,
    ...metadata,
  };
}

function vector() {
  return {
    as_of: "2026-10-23T00:00:00",
    sigma: metric(0.12, 1.2, "ok", { window_weeks: 52 }),
    ES: metric(-0.01, -0.5, "ok", { window_weeks: 156, observation_count: 156 }),
    beta_gold: metric(-0.25, -0.3),
    beta_us_equity: metric(0.8, 0.5),
    beta_japan_equity: metric(0, null),
    beta_us_treasury: metric(-0.1, -0.2),
    beta_japan_bond: metric(0.4, 0.7),
  };
}

function history() {
  return Array.from({ length: 52 }, (_, index) => {
    const point = vector();
    point.as_of = new Date(Date.UTC(2025, 9, 31 + index * 7)).toISOString();
    point.sigma.normalized = Math.sin(index / 7);
    point.ES.normalized = Math.cos(index / 9);
    point.beta_us_equity.value = Math.sin(index / 8);
    if (index === 30) {
      point.beta_gold.normalized = null;
      point.beta_gold.normalization_status = "iqr_below_threshold";
      point.beta_gold.value = null;
      point.beta_gold.status = "zero_variance";
    }
    return point;
  });
}

function snapshot() {
  return {
    asset_symbol: "TEST",
    generated_at: "2026-10-25T00:00:00Z",
    price_fields: { TEST: "Adj Close" },
    fx_alignment: "exact_calendar_date_no_fill",
    asset: vector(),
    asset_history: history(),
    portfolio: null,
    portfolio_history: null,
    portfolio_holdings: null,
    portfolio_status: "not_configured",
    portfolio_reason: "portfolio_configuration_is_null",
    portfolio_mode: null,
  };
}

function fakeDocument() {
  const elements = new Map();
  return {
    elements,
    querySelector(selector) {
      if (!elements.has(selector)) {
        elements.set(selector, {
          textContent: "",
          innerHTML: "",
          hidden: false,
          attributes: {},
          listeners: {},
          classes: [],
          setAttribute(name, value) { this.attributes[name] = value; },
          addEventListener(name, handler) { this.listeners[name] = handler; },
          classList: {
            add(name) { if (!this.owner.classes.includes(name)) this.owner.classes.push(name); },
            remove(name) { this.owner.classes = this.owner.classes.filter((item) => item !== name); },
          },
        });
        elements.get(selector).classList.owner = elements.get(selector);
      }
      return elements.get(selector);
    },
  };
}

test("radar uses one linear signed scale with zero at the middle ring", () => {
  const sample = vector();
  sample.beta_gold = metric(-3);
  sample.beta_us_equity = metric(0);
  sample.beta_japan_equity = metric(3);
  const model = ui.buildRadarModel(sample);
  const distance = (point) => Math.hypot(point.x - model.cx, point.y - model.cy);

  assert.equal(model.axes.length, 5);
  assert.equal(distance(model.axes[0].point), 0);
  assert.ok(Math.abs(distance(model.axes[1].point) - model.radius / 2) < 1e-9);
  assert.ok(Math.abs(distance(model.axes[2].point) - model.radius) < 1e-9);
  assert.equal(ui.BETA_LIMIT, 3);
});

test("all-positive and all-negative beta sets stay on their intended side of zero", () => {
  for (const [value, expectedSide] of [[1.25, "outside"], [-1.25, "inside"]]) {
    const sample = vector();
    for (const axis of ui.BETA_AXES) sample[axis.key] = metric(value);
    const model = ui.buildRadarModel(sample);
    const radii = model.axes.map((point) => Math.hypot(point.point.x - model.cx, point.point.y - model.cy));
    if (expectedSide === "outside") assert.ok(radii.every((radius) => radius > model.radius / 2));
    else assert.ok(radii.every((radius) => radius < model.radius / 2));
  }
});

test("positive, negative, zero and clipped beta retain raw values and axis identity", () => {
  const sample = vector();
  sample.beta_gold = metric(-4);
  sample.beta_us_equity = metric(3);
  sample.beta_japan_equity = metric(0);
  const model = ui.buildRadarModel(sample);

  assert.deepEqual(model.axes.map((axis) => axis.ticker), ["1540.T", "^GSPC", "1306.T", "TLT", "2510.T"]);
  assert.equal(model.axes[0].value, -4);
  assert.equal(model.axes[0].clipped, true);
  assert.equal(model.axes[0].point.x, model.cx);
  assert.equal(model.axes[1].clipped, false);
  assert.ok(Math.abs(
    Math.hypot(model.axes[2].point.x - model.cx, model.axes[2].point.y - model.cy) - model.radius / 2,
  ) < 1e-9);
  const html = ui.renderBetaSensitivity(sample);
  assert.match(html, /-4\.000/);
  assert.match(html, /範囲超過/);
  assert.match(html, /\+3\.000/);
  assert.match(html, /0\.000/);
});

test("unavailable radar axes are null and do not close the polygon through zero", () => {
  const sample = vector();
  sample.beta_japan_equity = metric(null, null, "missing_fx");
  const model = ui.buildRadarModel(sample);
  assert.equal(model.axes[2].point, null);
  assert.equal(model.polygon, null);
  assert.equal(model.segments.length, 3);
  assert.match(ui.renderBetaSensitivity(sample), /為替欠損/);
});

test("risk cards use annualized sigma and signed ES percentage labels", () => {
  const html = ui.renderRiskCards(vector());
  assert.match(html, /年率変動性（σ）/);
  assert.match(html, /週次標本標準偏差 × √52/);
  assert.match(html, /ES 95%（損失上位8週の平均）/);
  assert.match(html, /-1\.00%/);
  assert.match(html, /対象156週・有効観測156/);
});

test("normalized and raw beta trends are separate and missing weeks break lines", () => {
  const rows = history();
  const normalized = ui.buildLineModel(rows, "beta_gold", "normalized");
  const raw = ui.buildLineModel(rows, "beta_gold", "value");
  assert.equal(normalized.points.length, 52);
  assert.equal(normalized.points[30].value, null);
  assert.equal(normalized.segments.length, 49);
  assert.equal(raw.segments.length, 49);
  assert.match(ui.renderNormalizationHistory(rows), /正規化7指標/);
  assert.match(ui.renderBetaHistory(rows), /実測βの推移/);
  assert.match(ui.renderLineChart(rows, { key: "beta_gold", label: "Gold β" }, "normalized"), /最新 .*状態/);
});

test("extreme normalized values remain finite in their own chart scale", () => {
  const rows = history();
  rows[20].beta_gold.normalized = 1e300;
  const model = ui.buildLineModel(rows, "beta_gold", "normalized");
  assert.ok(model.points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));
});

test("portfolio not configured and calculation errors have distinct messages", () => {
  assert.match(ui.portfolioMessage({ portfolio: null, portfolio_status: "not_configured" }), /未設定/);
  assert.match(
    ui.portfolioMessage({ portfolio: { status: "configuration_error", reason: "weights_missing" }, portfolio_status: "configuration_error" }),
    /設定エラー: weights_missing/,
  );
  assert.match(ui.renderPortfolioPage(snapshot()), /ポートフォリオ未設定/);
});

test("portfolio mode and weights are visible without substituting sample values", () => {
  const input = snapshot();
  input.portfolio_mode = "scenario";
  input.portfolio_status = "ok";
  input.portfolio_reason = null;
  input.portfolio = { ...vector(), analysis_mode: "scenario", portfolio_diagnostics: { valid_weeks: 52, invalid_weeks: 0 } };
  input.portfolio_history = history().map((row) => ({ ...row, analysis_mode: "scenario" }));
  input.portfolio_holdings = { as_of: null, weights: { "7203.T": 0.75, "1540.T": 0.25 } };
  const html = ui.renderPortfolioPage(input);
  assert.match(html, /シナリオ分析/);
  assert.match(html, /7203\.T: 75\.00%/);
  assert.match(html, /1540\.T: 25\.00%/);
  assert.doesNotMatch(ui.renderPortfolioPage(snapshot()), /サンプル/);
});

test("checked-in calculation JSON renders current values and unavailable history honestly", async () => {
  const snapshotPath = path.join(__dirname, "../data/layer1/7203.T_risk_vector.json");
  const actual = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
  const doc = fakeDocument();
  await ui.loadSnapshot(doc, async () => ({ ok: true, async json() { return actual; } }));

  assert.equal(doc.querySelector("#status").textContent, "計算データを読み込みました");
  assert.match(doc.querySelector("#individual-page").innerHTML, /US Equity/);
  assert.match(doc.querySelector("#individual-page").innerHTML, /正規化7指標/);
  assert.match(doc.querySelector("#individual-page").innerHTML, /履歴データがありません/);
  assert.ok(doc.querySelector("#individual-page").innerHTML.includes(
    ui.formatValue("beta_us_equity", actual.asset.beta_us_equity.value),
  ));
  assert.match(doc.querySelector("#portfolio-page").innerHTML, /ポートフォリオ未設定/);
  assert.equal(doc.querySelector("#portfolio-page").hidden, true);
  assert.equal(doc.querySelector("#individual-tab").attributes["aria-selected"], "true");
  assert.match(doc.querySelector("#sources").textContent, /生成/);
});

test("missing or malformed JSON produces an explicit error state", async () => {
  for (const fetcher of [
    async () => ({ ok: false }),
    async () => ({ ok: true, async json() { throw new Error("invalid json"); } }),
    async () => ({ ok: true, async json() { return { asset: null }; } }),
  ]) {
    const doc = fakeDocument();
    await ui.loadSnapshot(doc, fetcher);
    assert.equal(doc.querySelector("#status").textContent, "計算結果なし");
    assert.ok(doc.querySelector("#status").classes.includes("error"));
  }
});
