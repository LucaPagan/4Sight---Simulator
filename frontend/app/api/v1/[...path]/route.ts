import { NextRequest } from "next/server";

async function proxy(req: NextRequest, context: { params: Promise<{path: string[]}> }) {
  const {path} = await context.params;
  const backend = process.env.API_BASE_URL || "http://127.0.0.1:8000";
  const url = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`, backend);
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const origin = req.headers.get("origin");
  if (origin) headers.set("origin", origin);
  try {
    const response = await fetch(url, { method: req.method, headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer(), cache: "no-store",
      signal: AbortSignal.timeout(180000) });
    const resultHeaders = new Headers();
    for (const key of ["content-type", "content-disposition"]) {
      const value = response.headers.get(key); if (value) resultHeaders.set(key, value);
    }
    return new Response(response.body, { status: response.status, headers: resultHeaders });
  } catch {
    return Response.json({detail: "Backend non raggiungibile. Avvia il servizio Python sulla porta 8000."}, {status: 503});
  }
}
export { proxy as GET, proxy as POST };
