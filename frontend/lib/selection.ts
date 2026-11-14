export function validCreative(rows: {ad_id: string}[], requested: string): string {
  return rows.some(row => row.ad_id === requested) ? requested : rows[0]?.ad_id || "";
}

export function isRunResumable(run: {status: string; completion_status: string; heartbeat_at?: string | null; created_at?: string | null}, now = Date.now()): boolean {
  if (run.completion_status === "complete") return false;
  if (["waiting_for_runtime", "waiting_for_capacity", "failed", "canceled"].includes(run.status)) return true;
  const heartbeat = Date.parse(run.heartbeat_at || run.created_at || "");
  return run.status === "running" && Number.isFinite(heartbeat) && now - heartbeat >= 600000;
}
