"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const ui = require("../reports/risk-vector-preview.js");

function metric(value, normalized = value) {
  return {
    value,
    normalized,
    status: "ok",
    normalization_status: normalized === null ? "configuration_error" : "ok",
  };
}

function vector() {
  return {
    sigma: metric(0.12, 1.2),
    ES: metric(-0.01, -0.5),
    beta_gold: metric(-0.25, -0.3),
    beta_us_equity: metric(0.8, 0.5),
    beta_japan_equity: metric(0.2, null),
    beta_us_treasury: metric(-0.1, -0.2),
    beta_japan_bond: metric(0.4, 0.7),
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
          classes: [],
          classList: { add(name) { this.owner.classes.push(name); } },
        });
        elements.get(selector).classList.owner = elements.get(selector);
      }
      return elements.get(selector);
    },
  };
}

test("beta raw values retain signed dimensionless formatting", () => {
  assert.equal(ui.formatValue("beta_gold", -0.25), "-0.250");
  assert.equal(ui.formatValue("sigma", 0.12), "12.00%");
  assert.equal(ui.formatValue("ES", -0.01), "-1.00%");
});

test("null normalized metric is omitted from radar points, not drawn as zero", () => {
  const model = ui.buildRadarModel(vector());

  assert.equal(model.points.length, 7);
  assert.equal(model.points[4], null);
  assert.equal(model.segments.length, 5);
  assert.ok(!model.segments.some(([a, b]) => a === model.points[4] || b === model.points[4]));
});

test("portfolio configuration absence and calculation failure have different messages", () => {
  assert.match(ui.portfolioMessage({ portfolio: null, portfolio_status: "not_configured" }), /未設定/);
  assert.match(
    ui.portfolioMessage({ portfolio: null, portfolio_status: "configuration_error", portfolio_reason: "weights_missing" }),
    /設定不足: weights_missing/,
  );
});

test("portfolio scenario is explicitly labeled in the rendered view", () => {
  const snapshot = {
    portfolio_mode: "scenario",
    portfolio: { ...vector(), analysis_mode: "scenario", portfolio_diagnostics: { valid_weeks: 2, invalid_weeks: 0 } },
  };

  assert.match(ui.renderPortfolio(snapshot), /シナリオ分析/);
});

test("missing vector is not substituted with demo values", () => {
  assert.match(ui.renderVector(null), /状態不明/);
  assert.doesNotMatch(ui.renderVector(null), /サンプル/);
});

test("generated JSON renders values, generation time, and unconfigured portfolio state", async () => {
  const doc = fakeDocument();
  await ui.loadSnapshot(doc, async () => ({
    ok: true,
    async json() {
      return {
        asset_symbol: "TEST",
        generated_at: "2026-01-01T00:00:00Z",
        asset: vector(),
        portfolio: null,
        portfolio_status: "not_configured",
        portfolio_reason: "portfolio_configuration_is_null",
      };
    },
  }));

  assert.match(doc.querySelector("#asset").innerHTML, /正規化リスクベクトル/);
  assert.match(doc.querySelector("#portfolio").innerHTML, /ポートフォリオ未設定/);
  assert.match(doc.querySelector("#sources").textContent, /生成/);
});

test("missing or malformed JSON produces an explicit error state", async () => {
  for (const fetcher of [
    async () => ({ ok: false }),
    async () => ({ ok: true, async json() { throw new Error("invalid json"); } }),
  ]) {
    const doc = fakeDocument();
    await ui.loadSnapshot(doc, fetcher);
    assert.equal(doc.querySelector("#status").textContent, "計算結果なし");
    assert.ok(doc.querySelector("#status").classes.includes("error"));
  }
});
