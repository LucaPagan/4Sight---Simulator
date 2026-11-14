import {test, expect, type Page} from "@playwright/test";

const ages = (base: number) => ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"].map((age_band, i) => ({
  age_band, impression_share: 1 / 6, ctr_estimate: base + i * 0.07, ctr_range: [base - 0.2, base + 0.4], expected_impressions: 1000, clicks_estimate: (base + i * 0.07) * 10, expected_spend: 8, evidence_level: "modeled_assumption"
}));
const prediction = (ad_id: string, ctr: number, cpm: number) => ({ad_id, date: "2026-11-16", ctr_pred: ctr, cpm_pred: cpm, ctr_interval: [ctr - 0.2, ctr + 0.2], cpm_interval: [cpm - 1, cpm + 1], expected_impressions: 6000, expected_clicks: ctr * 60, expected_spend: cpm * 6, ages: ages(ctr), cold_start: false, confidence_status: "ok"});
const profile = {agent_id: "agent-001", age_band: "25–34", category_affinity: 0.6, budget_sensitivity: 0.4, purchase_need: 0.5, brand_familiarity: 0.2, population_weight: 0.008, advertising_literacy: 0.5, repeat_tolerance: 0.5};
const run = {id: "run-0001", scenario_id: "sc-1", status: "succeeded", phase: "done", completion_status: "complete", progress: 100, completed_policies: 240, required_policies: 240, result_key: "k", created_at: "2026-11-14T10:00:00Z", provider: "ollama"};
const result = {
  completion_status: "complete", profiles: [profile],
  predictions: [prediction("creative-A", 1.84, 8.2), prediction("creative-B", 1.52, 7.9)],
  behavior: {raw_panel: [{ad_id: "creative-A", raw_panel_ctr: 2.1}], events: [{agent_id: "agent-001", ad_id: "creative-A", date: "2026-11-16", noticed: true, clicked: true, click_probability: 0.2, explanation: "Mi attira l'edizione limitata.", exposure_context: {calendar_regime: "x", state_before: {fatigue: 0, exposure_count: 0}}}]},
  comparison: {pairwise: [{a: "creative-A", b: "creative-B", probability_a_better: 0.8, probability_b_better: 0.2, difference_pp: 0.32, status: "model_superior", winner: "creative-A"}]},
  report: {limitations: ["Simulazione, non persone reali."], diagnoses: [{creative_id: "creative-A", hypothesis: "La scarsità aumenta l'attenzione.", claim_status: "hypothesis", experiment: {metric: "CTR", design: "Prova A contro una variante senza scarsità."}}]}
};

async function mockApi(page: Page, runs: unknown[] = [run]) {
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    const json = (body: unknown) => route.fulfill({json: body});
    if (path === "/simulations") return json(runs);
    if (path.endsWith("/status")) return json(run);
    if (path === "/predictions") return json(result);
    if (path === "/runtime/status") return json({available: true, ready: true, selected_model: "m", error: null});
    if (path === "/assets") return json([]);
    if (path === "/evidence") return json({sources: []});
    if (path === "/backtests") return json([]);
    if (path === "/scenarios/sc-1") return json({brief: {name: "Routine autunno", brand: "Nuvola", product_description: "Kit routine autunno", vertical: "beauty_skincare", objective: "vendite", platform: "meta", country: "IT", date_from: "2026-11-16", date_to: "2026-11-16", daily_adset_budget_eur: 150, population_size: 120, creatives: [{id: "creative-A", headline: "Edizione limitata: kit routine autunno", primary_text: "x", format: "carosello", lever: "scarcity"}, {id: "creative-B", headline: "Una routine semplice, ogni giorno", primary_text: "y", format: "video", lever: "value"}], seed: 42, age_shares: [], age_effects: [], sensitivity_profile: "central", prior_strength: 1, placement: "instagram_feed", browsing_task: "casual_scrolling", price_eur: null, notes: ""}});
    if (path === "/scenarios") return json({id: "sc-1", population_id: "pop-1"});
    if (path === "/populations/pop-1") return json({profiles: Array.from({length: 120}, (_, i) => ({...profile, agent_id: `agent-${i}`}))});
    if (path === "/simulations/preflight") return json({required_policies: 240, cached_policies: 0, estimated_seconds: 600, estimate_note: "", runtime: {ready: true}});
    return json({});
  });
}

test("campaign, audience and review steps", async ({page}) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Descrivi la campagna"})).toBeVisible();
  const next = page.getByRole("button", {name: /Continua al pubblico/});
  await expect(next).toBeDisabled();
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  await expect(page.getByLabel("Nome della campagna")).not.toHaveValue("");
  await next.click();
  await expect(page.getByRole("heading", {name: "Chi vedrà l'annuncio"})).toBeVisible();
  await page.getByText("Avanzate: quote per età e controlli esperti").click();
  for (const band of ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"]) {
    await expect(page.getByLabel(`Quota ${band}`)).toBeVisible();
  }
  await page.getByRole("button", {name: /Continua al riepilogo/}).click();
  await expect(page.getByRole("heading", {name: "Controlla e avvia"})).toBeVisible();
  await expect(page.getByText(/240 valutazioni/).first()).toBeVisible();
  await expect(page.getByRole("button", {name: "Avvia simulazione"})).toBeEnabled();
});

test("results give a verdict first", async ({page}) => {
  await mockApi(page);
  await page.goto("/results/run-0001");
  await expect(page.getByRole("heading", {name: "Vince la creatività A"})).toBeVisible();
  await expect(page.getByRole("row", {name: /Creatività B/})).toBeVisible();
  await expect(page.getByText("Come cambia per età")).toBeVisible();
  await page.screenshot({path: "../.impeccable/review/results-desktop.png", fullPage: true});
});

test("simulations list and settings tabs", async ({page}) => {
  await mockApi(page);
  await page.goto("/runs");
  await expect(page.getByRole("link", {name: /Simulazione del 14 nov/})).toBeVisible();
  await page.goto("/settings");
  await page.getByRole("tab", {name: "Fonti e metodo"}).click();
  await expect(page.getByText("Cosa è un dato e cosa è un'ipotesi")).toBeVisible();
  await page.getByRole("tab", {name: "Qualità del modello"}).click();
  await expect(page.getByRole("button", {name: "Verifica ora"})).toBeVisible();
});

test("phone layout has no horizontal scroll and a bottom navigation", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await mockApi(page);
  for (const path of ["/", "/runs", "/settings", "/results/run-0001"]) {
    await page.goto(path);
    await expect(page.getByRole("navigation", {name: "Navigazione principale"})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), path).toBeTruthy();
  }
  await page.goto("/results/run-0001");
  await expect(page.getByRole("heading", {name: "Vince la creatività A"})).toBeVisible();
  await page.screenshot({path: "../.impeccable/review/results-mobile.png", fullPage: true});
});
