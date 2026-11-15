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

const catalog = {
  placements: [{id: "instagram_feed", label: "Instagram Feed", platform: "instagram", surface: "feed"}, {id: "instagram_stories", label: "Instagram Stories", platform: "instagram", surface: "stories"}, {id: "facebook_feed", label: "Facebook Feed", platform: "facebook", surface: "feed"}],
  terms: [{id: "interest:dogs", kind: "interest", label: "Interesse: Cani", modelled: true}, {id: "demographic:single", kind: "demographic", label: "Demografia: Single", modelled: true}, {id: "interest:travel", kind: "interest", label: "Interesse: Viaggi", modelled: false}],
  attributes: []
};
const reading = {
  constraints: [{attribute: "pet_species", values: ["dog"], negate: false}, {attribute: "household", values: ["alone"], negate: false}],
  unrecognized_intent: "", placements: [], applied_to_population: false, reading: "rules_v1", reach: null,
  proxies: [
    {attribute: "pet_species", values: ["dog"], meta_direct: false, suggested_terms: ["interest:dogs"], selected_terms: [], expected_precision: null, precision_evidence: "assumption"},
    {attribute: "household", values: ["alone"], meta_direct: false, suggested_terms: ["demographic:single"], selected_terms: [], expected_precision: null, precision_evidence: "assumption"}
  ],
  notes: [{code: "not_targetable", severity: "warning", message: "«Composizione del nucleo» non è un'opzione di Ads Manager: si raggiunge solo con proxy."}]
};
const targetingReport = {
  ...reading, applied_to_population: true,
  notes: [{code: "ideal_share", severity: "warning", message: "Stima: circa il 5% di chi vedrebbe l'annuncio rientra nel target ideale."}],
  reach: {method: "importance_resampling_v1", evidence: "assumption", pool_size: 24000, age_shares: [0.15, 0.2, 0.21, 0.24, 0.18, 0.02], ideal_share_in_reached: 0.054, ideal_share_in_base: 0.026, lift: 2.1, unmodelled_terms: [],
    constraints: [{attribute: "pet_species", values: ["dog"], negate: false, share_in_reached: 0.55, share_in_base: 0.24}, {attribute: "household", values: ["alone"], negate: false, share_in_reached: 0.15, share_in_base: 0.19}],
    audit: {size: 120, duplicates: 0, min_distance: 0.13, mean_distance: 0.46, band_counts: {}, reach_effective_ratio: 0.5, missing_values: [], status: "ok", warnings: []}}
};
const decision = {first_impression: "Ho un cane, mi sono fermato sulla ciotola.", detail_cited: "ciotola", read_beyond_glance: true, reaction_after_stopping: "Gli ingredienti sembrano semplici.", skip_per_100: 70, stop_per_100: 15, engage_per_100: 5, click_per_100: 10, action_if_engaged: "save", post_click_intent: "browse", frictions: [], evidence: ["ad.visual"], unknowns: [], gates: {notice: 0.3, engage: 0.15, click: 0.1}};
const nativeRun = {...run, mode: "agent_native", slots: ["first", "repeat", "saturated"]};
const nativeResult = {
  ...result, mode: "agent_native", validated: false, quantitative_source: "agent_native_decisions",
  comparison: {pairwise: [{a: "creative-A", b: "creative-B", probability_a_better: 0.9, probability_b_better: 0.1, difference_pp: 0.32, status: "winner_under_model", winner: "creative-A", decision: "out_of_domain", model_leader: "creative-A"}], domain_assessment: {status: "out_of_domain", reason: "Nessun benchmark indipendente ha ancora verificato un dominio.", verified: false}},
  profiles: [{...profile, age: 34, household: "alone", pet_species: "dog", income_band: "mid", in_ideal_target: true}, {...profile, agent_id: "agent-002", age: 52, household: "family", pet_species: "none", income_band: "high", in_ideal_target: false}],
  cards: {
    "agent-001": {name: "Giulia Ferri", city: "Bologna", job: "infermiera", bio: "Vive da sola con il suo labrador.", daily_routine: "Turni in ospedale.", category_relationship: "Compra crocchette online.", social_habits: "Scorre Instagram la sera.", ad_reaction_style: "Salta quasi tutto.", pain_points: ["poco tempo"], quirks: ["compra all'ultimo"], facts: ["Ha un cane."], source: "llm"},
    "agent-002": {name: "Persona 2", city: "non specificata", job: "dipendente", bio: "Ha 52 anni.", daily_routine: "Non descritta.", category_relationship: "Non ha animali.", social_habits: "Usa Facebook.", ad_reaction_style: "Non descritta.", pain_points: [], quirks: [], facts: ["Non ha animali domestici."], source: "template"}
  },
  decision_snapshot: [{agent_id: "agent-001", creative_id: "creative-A", slot: "first", regime: "ordinary", placement: "instagram_feed", decision}],
  predictions: [{...prediction("creative-A", 1.84, 8.2), reference_forecast: {ctr_pred: 0.9, ctr_interval: [0.7, 1.1], expected_clicks: 5}}, {...prediction("creative-B", 1.52, 7.9), reference_forecast: {ctr_pred: 0.8, ctr_interval: [0.6, 1.0], expected_clicks: 4}}],
  behavior: {raw_panel: [], events: [{agent_id: "agent-001", ad_id: "creative-A", date: "2026-11-16", noticed: true, clicked: false, outcome: "engaged", slot: "first", click_probability: 0.1, explanation: "Ho un cane, mi sono fermato sulla ciotola.", exposure_context: {calendar_regime: "ordinary"}}]},
  report: {
    limitations: ["Modalità agent_native non validata"], diagnoses: [],
    reaction_quality: {decisions: 240, flags: ["positivity_bias"], warnings: [], grounded_share: 0.82, positive_share: 0.4, marketer_language_share: 0, invented_numbers_share: 0, inconsistent_share: 0.02, mean_notice: 0.31, profile_dependence: {pet_species: {notice: 0.22, click: 0.1}}, human_validated: false},
    native: {
      engine_version: "agent-native-v1", slot_mix: {first: 0.45}, validated: false, uncertainty: "Intervalli da ricampionamento.", reach_share_by_age: {},
      divergence: [{ad_id: "creative-A", agent_native_ctr: 1.84, reference_ctr: 0.9, reference_interval: [0.7, 1.1], ratio: 2.04, flags: ["outside_reference_interval"], diverges: true}, {ad_id: "creative-B", agent_native_ctr: 1.52, reference_ctr: 0.8, reference_interval: [0.6, 1.0], ratio: 1.9, flags: [], diverges: false}],
      breakdowns: [{ad_id: "creative-A", segments: {pet_species: [{key: "dog", personas: 60, reach_share: 0.55, notice_rate: 0.3, engage_rate: 0.15, ctr_pct: 3.4, low_sample: false}, {key: "none", personas: 4, reach_share: 0.02, notice_rate: 0.05, engage_rate: 0.01, ctr_pct: 0.4, low_sample: true}]}}]
    }
  }
};

async function mockApi(page: Page, runs: unknown[] = [run], override: Record<string, unknown> = {}, extra: {run?: unknown; scenario?: Record<string, unknown>} = {}) {
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    const json = (body: unknown) => route.fulfill({json: body});
    if (path === "/simulations") return json(runs);
    if (path.endsWith("/status")) return json(extra.run ?? run);
    if (path === "/targeting/catalog") return json(catalog);
    if (path === "/targeting/analyze") return json(reading);
    if (path === "/predictions") return json({...result, ...override});
    if (path === "/runtime/status") return json({available: true, ready: true, selected_model: "m", error: null});
    if (path === "/assets") return json([]);
    if (path === "/evidence") return json({sources: []});
    if (path === "/backtests") return json([]);
    if (path === "/scenarios/sc-1") return json({...(extra.scenario ?? {}), brief: {name: "Routine autunno", brand: "Nuvola", product_description: "Kit routine autunno", vertical: "beauty_skincare", objective: "vendite", platform: "meta", country: "IT", date_from: "2026-11-16", date_to: "2026-11-16", daily_adset_budget_eur: 150, population_size: 120, creatives: [{id: "creative-A", headline: "Edizione limitata: kit routine autunno", primary_text: "x", format: "carosello", lever: "scarcity"}, {id: "creative-B", headline: "Una routine semplice, ogni giorno", primary_text: "y", format: "video", lever: "value"}], seed: 42, age_shares: [], age_effects: [], sensitivity_profile: "central", prior_strength: 1, placement: "instagram_feed", browsing_task: "casual_scrolling", price_eur: null, notes: ""}});
    if (path === "/scenarios") return json({id: "sc-1", population_id: "pop-1"});
    if (path === "/populations/pop-1") return json({profiles: Array.from({length: 120}, (_, i) => ({...profile, agent_id: `agent-${i}`}))});
    if (path === "/simulations/preflight") return json({required_policies: 240, cached_policies: 0, estimated_seconds: 600, estimate_note: "", runtime: {ready: true}});
    return json({});
  });
}

test("one page: describe the campaign and launch", async ({page}) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Quale annuncio funziona meglio?"})).toBeVisible();
  const launch = page.getByRole("button", {name: "Avvia simulazione"});
  await expect(launch).toBeDisabled();
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  await expect(page.getByLabel("Nome")).not.toHaveValue("");
  await expect(launch).toBeEnabled();
  // Niente controlli da esperti nel percorso principale.
  for (const gone of ["Codice per ripetere lo stesso risultato", "Inverti le differenze tra le età", "Quota 18–24"]) {
    await expect(page.getByText(gone)).toHaveCount(0);
  }
  const request = page.waitForRequest(r => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/simulations"));
  await launch.click();
  expect((await request).postDataJSON()).toMatchObject({scenario_id: "sc-1", provider: "ollama"});
});

test("results give a verdict first", async ({page}) => {
  await mockApi(page);
  await page.goto("/results/run-0001");
  await expect(page.getByRole("heading", {name: "Vince la creatività A"})).toBeVisible();
  await expect(page.getByRole("row", {name: /Creatività B/})).toBeVisible();
  await expect(page.getByText("Come cambia per età")).toBeVisible();
  await page.screenshot({path: "../.impeccable/review/results-desktop.png", fullPage: true});
});

test("out-of-domain comparison gives no verified winner", async ({page}) => {
  const outOfDomain = {
    pairwise: [{a: "creative-A", b: "creative-B", probability_a_better: 0.99, probability_b_better: 0.01, difference_pp: 0.32, status: "winner_under_model", winner: "creative-A", decision: "out_of_domain", model_leader: "creative-A"}],
    domain_assessment: {status: "out_of_domain", reason: "Nessun benchmark indipendente ha ancora verificato un dominio.", verified: false}
  };
  await mockApi(page, [run], {comparison: outOfDomain});
  await page.goto("/results/run-0001");
  await expect(page.getByRole("heading", {name: "Nessun vincitore verificato"})).toBeVisible();
  await expect(page.getByText(/fuori dal dominio verificato/).first()).toBeVisible();
  await expect(page.getByText(/creatività A in vantaggio/)).toBeVisible();
  await expect(page.getByText("consigliata")).toHaveCount(0);
  await expect(page.getByRole("heading", {name: /Vince/})).toHaveCount(0);
});

test("offer, price and landing page reach the scenario request", async ({page}) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  const creative = page.locator("fieldset").first();
  await creative.getByText("Altri dettagli").click();
  await creative.getByLabel("Offerta").fill("-20% fino a domenica");
  await creative.getByLabel("Prezzo mostrato").fill("19,90 € invece di 24,90 €");
  await creative.getByLabel("Pagina dopo il clic").fill("Scheda prodotto con recensioni");
  const request = page.waitForRequest(r => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/scenarios"));
  await page.getByRole("button", {name: "Avvia simulazione"}).click();
  const body = (await request).postDataJSON();
  expect(body.creatives[0]).toMatchObject({offer: "-20% fino a domenica", price_text: "19,90 € invece di 24,90 €", landing_page_summary: "Scheda prodotto con recensioni"});
  expect(body).toMatchObject({seed: 42, prior_strength: 1, sensitivity_profile: "central"});
});

test("simulations list and a settings page that only holds the AI engine", async ({page}) => {
  await mockApi(page);
  await page.goto("/runs");
  await expect(page.getByRole("link", {name: /Simulazione del 14 nov/})).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByRole("heading", {name: "Motore AI"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Dove lavorano i consumatori simulati"})).toBeVisible();
  for (const gone of ["Fonti e metodo", "Qualità del modello", "Verifica ora", "Importa i dati del kit"]) {
    await expect(page.getByText(gone)).toHaveCount(0);
  }
  await expect(page.getByRole("tab")).toHaveCount(0);
});

test("without Ollama the engine page explains what to do and the app still launches", async ({page}) => {
  await mockApi(page);
  await page.route("**/api/v1/runtime/status**", route => route.fulfill({json: {available: false, ready: false, selected_model: "qwen3.5:4b", recommended_model: "qwen3.5:4b", error: "Runtime locale non disponibile"}}));
  await page.goto("/settings");
  await expect(page.getByText("OLLAMA NON ATTIVO")).toBeVisible();
  await expect(page.getByRole("link", {name: "ollama.com/download"})).toBeVisible();
  await page.goto("/");
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  await expect(page.getByRole("button", {name: "Avvia simulazione"})).toBeEnabled();
  await expect(page.getByText(/Il motore AI non è pronto/)).toBeVisible();
});

test("a missing local model offers a one-click download", async ({page}) => {
  await mockApi(page);
  await page.route("**/api/v1/runtime/status**", route => route.fulfill({json: {available: true, ready: false, selected_model: "qwen3.5:4b", recommended_model: "qwen3.5:4b", error: "Modello selezionato non installato"}}));
  await page.route("**/api/v1/runtime/pull", route => route.fulfill({status: route.request().method() === "POST" ? 202 : 200, json: {status: "downloading", model: "qwen3.5:4b", completed: 1e9, total: 3.3e9, message: "pulling"}}));
  await page.goto("/settings");
  await expect(page.getByText("MODELLO DA SCARICARE")).toBeVisible();
  await expect(page.getByRole("progressbar")).toBeVisible();
});

test("phone layout has no horizontal scroll and a top navigation", async ({page}) => {
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


test("describe the audience: reading, proxy suggestions and the experimental mode", async ({page}) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  const personas = page.getByRole("radio", {name: /Persone simulate/});
  await expect(personas).toBeDisabled();
  await page.getByLabel("Descrivi il pubblico con parole tue").fill("chi ha un cane e vive da solo");
  await expect(page.getByRole("heading", {name: "Come l'ho capito"})).toBeVisible();
  await expect(page.getByText("ha un cane", {exact: true})).toBeVisible();
  await expect(page.getByText(/non è un'opzione di Ads Manager/)).toBeVisible();
  await page.getByRole("button", {name: /Interesse: Cani/}).click();
  await page.getByText("Impostazioni come in Ads Manager").click();
  await expect(page.getByText("Interesse: Cani").first()).toBeVisible();
  await expect(personas).toBeEnabled();
  await personas.check();
  await page.screenshot({path: "../.impeccable/review/audience-form-desktop.png", fullPage: true});
  await expect(page.getByText(/non è stato validato|Nessuna campagna reale/).first()).toBeVisible();
  await page.getByLabel("Considera anche chi ha già visto l'annuncio più volte").uncheck();
  const scenario = page.waitForRequest(r => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/scenarios"));
  const simulation = page.waitForRequest(r => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/simulations"));
  await page.getByRole("button", {name: "Avvia simulazione"}).click();
  const body = (await scenario).postDataJSON();
  expect(body.targeting).toMatchObject({audience_intent: "chi ha un cane e vive da solo", detailed: [{id: "interest:dogs", mode: "include"}]});
  expect((await simulation).postDataJSON()).toMatchObject({mode: "agent_native", slots: ["first"]});
});

test("without a described audience nothing about targeting is sent", async ({page}) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  const scenario = page.waitForRequest(r => r.method() === "POST" && new URL(r.url()).pathname.endsWith("/scenarios"));
  await page.getByRole("button", {name: "Avvia simulazione"}).click();
  expect("targeting" in (await scenario).postDataJSON()).toBeFalsy();
});

test("simulated-people results show the label, the reach, the historical reference and the personas", async ({page}) => {
  await mockApi(page, [nativeRun], nativeResult, {run: nativeRun, scenario: {targeting_report: targetingReport}});
  await page.goto("/results/run-0001");
  await expect(page.getByText("Persone simulate · non validato").first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Nessun vincitore verificato"})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Chi raggiunge davvero"})).toBeVisible();
  await expect(page.getByText(/rientra nel pubblico che volevi/)).toBeVisible();
  await expect(page.getByRole("heading", {name: "Persone simulate e dati storici"})).toBeVisible();
  await expect(page.getByText("Molto diverso")).toBeVisible();
  await expect(page.getByRole("heading", {name: "Chi reagisce di più"})).toBeVisible();
  await expect(page.getByText("pochi casi")).toBeVisible();
  await expect(page.getByRole("heading", {name: "Le persone simulate"})).toBeVisible();
  await expect(page.getByText("Giulia Ferri")).toBeVisible();
  await expect(page.getByText(/mi sono fermato sulla ciotola/).first()).toBeVisible();
  await page.getByLabel("Mostra").selectOption("other");
  await expect(page.getByText("Giulia Ferri")).toHaveCount(0);
  await expect(page.getByText("Scheda essenziale", {exact: true})).toBeVisible();
  await expect(page.getByText("Le decisioni non cambiano con il profilo")).toHaveCount(0);
  await expect(page.getByText("Troppe persone sembrano interessate")).toBeVisible();
  await expect(page.getByRole("button", {name: "Scarica la rubrica per i valutatori"})).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path: "../.impeccable/review/results-native-desktop.png", fullPage: true});
});

test("simulated-people results fit a phone", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await mockApi(page, [nativeRun], nativeResult, {run: nativeRun, scenario: {targeting_report: targetingReport}});
  await page.goto("/results/run-0001");
  await expect(page.getByRole("heading", {name: "Le persone simulate"})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.goto("/");
  await page.getByRole("button", {name: "Compila con un esempio"}).click();
  await page.getByLabel("Descrivi il pubblico con parole tue").fill("chi ha un cane");
  await page.getByText("Impostazioni come in Ads Manager").click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("native persona progress shows attempts and rejects without hiding provider errors", async ({page}) => {
  const running = {...run, status: "running", completion_status: "partial", phase: "personas", mode: "agent_native", progress: 4, completed_policies: 0, required_policies: 720, persona_cards_done: 2, persona_cards_total: 120,
    error: "Quota temporanea: riprendi più tardi", performance: {cards: {attempts: 18, rejected: 16, cache_hits: 0}, reactions: {cache_hits: 0}}};
  await mockApi(page, [running], {completion_status: "preliminary"}, {run: running});
  await page.goto("/results/run-0001");
  await expect(page.getByText(/2 di 120 schede/)).toBeVisible();
  await expect(page.getByText(/18 tentativi.*16 scarti/)).toBeVisible();
  await expect(page.getByText(running.error)).toBeVisible();
});

test("native reaction progress shows cached reactions and supports historical runs", async ({page}) => {
  const running = {...run, status: "running", completion_status: "partial", phase: "agents", mode: "agent_native", progress: 20, completed_policies: 30, required_policies: 720,
    performance: {cards: {}, reactions: {cache_hits: 12}}};
  await mockApi(page, [running], {completion_status: "preliminary"}, {run: running});
  await page.goto("/results/run-0001");
  await expect(page.getByText(/30 di 720 reazioni/)).toBeVisible();
  await expect(page.getByText(/12.*cache/)).toBeVisible();
});
