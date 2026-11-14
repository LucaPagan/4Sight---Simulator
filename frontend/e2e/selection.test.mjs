import {test} from "node:test";
import assert from "node:assert/strict";
import {validCreative} from "../lib/selection.ts";

test("history selection falls back to a creative in the opened run",()=>{
  assert.equal(validCreative([{ad_id:"A"},{ad_id:"B"}],"removed-C"),"A");
  assert.equal(validCreative([{ad_id:"A"},{ad_id:"B"}],"B"),"B");
  assert.equal(validCreative([],"C"),"");
});


test("interrupted workers can resume; complete and live runs stay terminal or active", async () => {
  const {isRunResumable} = await import("../lib/selection.ts");
  assert.equal(isRunResumable({status:"running",completion_status:"partial",heartbeat_at:"2026-11-14T12:00:00Z"},Date.parse("2026-11-14T12:11:00Z")),true);
  assert.equal(isRunResumable({status:"running",completion_status:"partial",heartbeat_at:"2026-11-14T12:00:00Z"},Date.parse("2026-11-14T12:01:00Z")),false);
  assert.equal(isRunResumable({status:"succeeded",completion_status:"complete"}),false);
});
