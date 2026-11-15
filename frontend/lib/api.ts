export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, body === undefined ? {cache: "no-store"} : {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
  const json = await response.json().catch(() => ({detail: "Il servizio ha risposto in modo inatteso. Riprova tra poco."}));
  if (!response.ok) {
    const detail = json.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((e: {msg: string}) => e.msg).join(" · ") : "Richiesta non riuscita");
  }
  return json as T;
}
