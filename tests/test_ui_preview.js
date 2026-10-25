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

test("raw beta values retain sign and risk metrics use percentage formatting", () => {
  assert.equal(ui.formatValue("beta_gold", -0.25), "-0.250");
  assert.equal(ui.formatValue("beta_us_equity", 0.25), "+0.250");
  assert.equal(ui.formatValue("beta_japan_equity", 0), "0.000");
  assert.equal(ui.formatValue("sigma", 0.12), "12.00%");
  assert.equal(ui.formatValue("ES", -0.01), "-1.00%");
});

test("beta diverging bars use raw beta, a common +/-3 scale, and explicit clipping", () => {
  const sample = vector();
  sample.beta_gold = metric(-4, -1e9);
  sample.beta_us_equity = metric(1.5, 1e9);
  sample.beta_japan_equity = metric(0, -1e12);
  const model = ui.buildBetaBarModel(sample);

  assert.equal(model.length, 5);
  assert.equal(model[0].value, -4);
  assert.equal(model[0].clipped, true);
  assert.equal(model[0].left, 0);
  assert.equal(model[0].width, 50);
  assert.equal(model[1].left, 50);
  assert.equal(model[1].width, 25);
  assert.equal(model[1].window_weeks, 52);
  assert.equal(model[1].observation_count, 52);
  assert.equal(model[2].zero, true);
  assert.equal(model[2].width, 0);
  assert.equal(ui.BETA_DISPLAY_LIMIT, 3);
});

test("null and error beta metrics do not become zero bars", () => {
  const sample = vector();
  sample.beta_gold = metric(null, null, "missing_fx");
  sample.beta_japan_equity = metric(null, null, "ok");
  const model = ui.buildBetaBarModel(sample);
  assert.equal(model[0].value, null);
  assert.equal(model[0].width, 0);
  assert.equal(model[0].status, "missing_fx");
  assert.equal(model[2].status, "calculation_error");
  const html = ui.renderVector(sample);
  assert.match(html, /為替欠損/);
  assert.match(html, /計算エラー/);
  assert.doesNotMatch(html, /beta-fill negative.*Gold/s);
});

test("risk level cards distinguish annualized sigma from signed 95% ES", () => {
  const html = ui.renderVector(vector());
  assert.match(html, /σ 年率/);
  assert.match(html, /週次標本標準偏差 × √52/);
  assert.match(html, /ES 95%/);
  assert.match(html, /損失上位8週の符号付き平均/);
  assert.match(html, /-1\.00%/);
  assert.match(html, /対象 156週 · 有効観測 156/);
});

test("normalized values are auxiliary and do not control beta drawing", () => {
  const sample = vector();
  sample.beta_us_equity = metric(0.4, 1e100);
  const model = ui.buildBetaBarModel(sample);
  assert.equal(model[1].width, (0.4 / 3) * 50);
  const html = ui.renderVector(sample);
  assert.match(html, /過去分布に対する相対位置/);
  assert.match(html, /βの感応度や銘柄間の絶対リスクを表しません/);
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
  assert.match(ui.renderVector(null), /計算結果がありません/);
  assert.doesNotMatch(ui.renderVector(null), /サンプル/);
});

test("actual generated market JSON renders without synthetic fallback", async () => {
  const snapshotPath = path.join(__dirname, "../data/layer1/7203.T_risk_vector.json");
  const snapshot = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
  const doc = fakeDocument();
  await ui.loadSnapshot(doc, async () => ({ ok: true, async json() { return snapshot; } }));

  assert.equal(doc.querySelector("#status").textContent, "計算データを読み込みました");
  assert.match(doc.querySelector("#asset").innerHTML, /US Equity/);
  assert.ok(doc.querySelector("#asset").innerHTML.includes(
    ui.formatValue("beta_us_equity", snapshot.asset.beta_us_equity.value),
  ));
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
