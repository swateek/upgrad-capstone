// Server-side proxy to the FastAPI backend. API_URL is read at request time, so one image
// works locally (http://localhost:3401) and in docker-compose (http://api:8000).
// Only GET and POST are forwarded; there is no route here that can award, order or debar.

const API_URL = () => process.env.API_URL ?? "http://localhost:3401";
const ALLOWED = /^(health|domain|answer|chat|threads\/[A-Za-z0-9_-]+|listings\/[a-z0-9-]+|tools\/[a-z_]+)$/;

async function forward(req: Request, path: string[]): Promise<Response> {
  const target = path.join("/");
  if (!ALLOWED.test(target)) {
    return Response.json({ detail: "not found" }, { status: 404 });
  }
  try {
    const client = (req.headers.get("x-forwarded-for") ?? "").split(",")[0].trim() || "browser";
    const upstream = await fetch(`${API_URL()}/${target}`, {
      method: req.method,
      headers: { "content-type": "application/json", "x-forwarded-for": client },
      body: req.method === "POST" ? await req.text() : undefined,
      cache: "no-store",
    });
    const type = upstream.headers.get("content-type") ?? "application/json";
    if (type.startsWith("text/event-stream")) {
      // stream agent progress through unbuffered
      return new Response(upstream.body, {
        status: upstream.status,
        headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      });
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "The API is not reachable." }, { status: 502 });
  }
}

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path);
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path);
}
