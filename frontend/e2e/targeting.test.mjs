import {test} from "node:test";
import assert from "node:assert/strict";
import {hoursBetween, isTargetingActive, targetingProblems, toPayload} from "../lib/targeting.ts";

test("an empty or default targeting does not change the simulation", () => {
  assert.equal(isTargetingActive(undefined), false);
  assert.equal(isTargetingActive({}), false);
  assert.equal(isTargetingActive({audience_intent: "  ", age_min: 18, age_max: 65, gender: "all", advantage_placements: true}), false);
  assert.equal(isTargetingActive({audience_intent: "ha un cane"}), true);
  assert.equal(isTargetingActive({gender: "women"}), true);
  assert.equal(isTargetingActive({advantage_placements: false, placements: ["instagram_feed"]}), true);
});

test("problems the server would reject are named before launching", () => {
  assert.deepEqual(targetingProblems({age_min: 40, age_max: 30}), ["l'età minima è maggiore della massima"]);
  assert.deepEqual(targetingProblems({advantage_placements: false, placements: []}), ["nessun posizionamento scelto"]);
  assert.deepEqual(targetingProblems({bid_strategy: "cost_cap"}), ["l'importo dell'offerta"]);
  assert.deepEqual(targetingProblems({bid_strategy: "cost_cap", bid_amount_eur: 2}), []);
});

test("the payload drops what the form hides", () => {
  const sent = toPayload({audience_intent: " ha un cane ", advantage_placements: true, placements: ["instagram_feed"], bid_strategy: "lowest_cost", bid_amount_eur: 5});
  assert.equal(sent.audience_intent, "ha un cane");
  assert.deepEqual(sent.placements, []);
  assert.equal(sent.bid_amount_eur, null);
  assert.deepEqual(toPayload({advantage_placements: false, placements: ["instagram_feed"]}).placements, ["instagram_feed"]);
});

test("a time window wraps around midnight and equal ends mean the whole day", () => {
  assert.deepEqual(hoursBetween(22, 2), [22, 23, 0, 1]);
  assert.deepEqual(hoursBetween(8, 10), [8, 9]);
  assert.deepEqual(hoursBetween(0, 0), []);
});
