export type {AgePrediction as Age, Prediction, ConsumerProfile as Profile, TargetingReport, TargetingSpec, ReachSummary} from "./contracts.generated";
import type {SimulationRun, Prediction, ConsumerProfile, TargetingSpec} from "./contracts.generated";

export type Mode = "history_forecast" | "agent_native";
export type Slot = "first" | "repeat" | "saturated";
export type Run = SimulationRun & {mode?: Mode; slots?: Slot[] | null; persona_cards_done?: number; persona_cards_total?: number};

// Editable form drafts; API submission validates the generated CampaignBrief contract.
export type Creative = {id: string; headline: string; primary_text: string; visual_description: string; cta: string; lever: string; format: string; claim_verified: boolean; offer?: string; price_text?: string; landing_page_summary?: string};
export type Brief = {name: string; brand: string; product_description: string; vertical: string; objective: string; platform: string; country: string; date_from: string; date_to: string; daily_adset_budget_eur: number; creatives: Creative[]; population_size: number; seed: number; age_shares: number[]; age_effects: number[]; sensitivity_profile: string; prior_strength: number; placement: string; browsing_task: string; price_eur: number | null; notes: string; targeting?: TargetingSpec};
export type Event = {agent_id: string; ad_id: string; date: string; noticed: boolean; clicked: boolean; click_probability: number; explanation: string | null; outcome?: "skipped" | "stopped" | "engaged" | "clicked"; slot?: Slot; exposure_context: {calendar_regime: string; state_before?: {fatigue: number; exposure_count: number}}};

// Persone simulate (modalità agent_native)
export type Catalog = {
  placements: {id: string; label: string; platform: string; surface: string; desktop_only?: boolean}[];
  terms: {id: string; kind: string; label: string; modelled: boolean}[];
  attributes: {id: string; label: string; values: string[]; meta_direct: boolean}[];
};
export type PersonaCard = {name: string; city: string; job: string; bio: string; daily_routine: string; category_relationship: string; social_habits: string; ad_reaction_style: string; pain_points: string[]; quirks: string[]; facts: string[]; source: "llm" | "template"};
export type Decision = {first_impression: string; detail_cited: string; read_beyond_glance: boolean; reaction_after_stopping: string; skip_per_100: number; stop_per_100: number; engage_per_100: number; click_per_100: number; action_if_engaged: string; post_click_intent: string; frictions: string[]; evidence: string[]; unknowns: string[]; gates: {notice: number; engage: number; click: number}};
export type NativeProfile = ConsumerProfile & {age?: number; gender?: string; household?: string; has_children?: string; relationship_status?: string; pet_species?: string; urbanicity?: string; occupation?: string; income_band?: string; skincare_routine?: string; fitness_active?: string; in_ideal_target?: boolean; region?: string};
export type Segment = {key: string; personas: number; reach_share: number; notice_rate: number; engage_rate: number; ctr_pct: number; low_sample: boolean};
export type Divergence = {ad_id: string; agent_native_ctr: number; reference_ctr: number; reference_interval: number[]; ratio: number | null; flags: string[]; diverges: boolean};
export type Native = {engine_version: string; slot_mix: Record<string, number | Record<string, unknown>>; breakdowns: {ad_id: string; segments: Record<string, Segment[]>}[]; divergence: Divergence[]; reach_share_by_age: Record<string, number>; validated: boolean; uncertainty: string};
export type Quality = {decisions: number; flags: string[]; warnings: string[]; grounded_share: number; positive_share: number; marketer_language_share: number; invented_numbers_share: number; inconsistent_share: number; mean_notice: number; profile_dependence: Record<string, {notice: number; click: number}>; human_validated: boolean};
export type Snapshot = {agent_id: string; creative_id: string; slot: Slot; regime: string; placement: string; decision: Decision};

export type Result = {completion_status: string; mode?: Mode; validated?: boolean; quantitative_source?: string; profiles: NativeProfile[]; predictions: (Prediction & {reference_forecast?: {ctr_pred: number; ctr_interval: number[] | null; expected_clicks: number}})[]; cards?: Record<string, PersonaCard>; decision_snapshot?: Snapshot[]; persona_report?: {written_by_llm: number; template_fallback: number; from_cache: number} | null; model?: {name: string; digest: string; prompt_version?: string}; behavior?: {raw_panel: {ad_id: string; raw_panel_ctr: number}[]; events: Event[]; reaction_quality?: Quality}; report?: {limitations: string[]; native?: Native; reaction_quality?: Quality; diagnoses: {creative_id: string; hypothesis: string; claim_status: string; experiment: {metric: string; design: string}}[]}; comparison?: {pairwise: {a: string; b: string; probability_a_better: number; probability_b_better: number; difference_pp: number; status: string; winner: string | null; decision?: "winner" | "unresolvable_difference" | "out_of_domain"; model_leader?: string | null}[]; domain_assessment?: {status: string; reason: string; verified: boolean} | null}};
export type Runtime = {available: boolean; ready: boolean; selected_model: string; error: string | null; digest?: string};
