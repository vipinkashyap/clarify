// Clarify — arxiv API proxy (Cloudflare Worker).
//
// Arxiv's export.arxiv.org/api/query endpoint doesn't send CORS headers, so
// the browser can't fetch it directly. This Worker is a thin pass-through
// that adds the CORS header, caches responses briefly, and returns the raw
// Atom XML — the browser handles parsing via DOMParser.
//
// Endpoints:
//   GET /?q=attention&max=15     convenience: shorthand for search_query
//   GET /?search_query=cat:cs.CL&max_results=20&sortBy=submittedDate
//                                pass-through: arxiv's native API params
//
// Deploy: `wrangler deploy` from this directory (see ../README.md).

const ARXIV_API = "https://export.arxiv.org/api/query";
const CACHE_TTL_SECONDS = 300; // 5 minutes
const MAX_RESULTS_CAP = 50;

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return cors(new Response(null, { status: 204 }));
    }
    if (request.method !== "GET") {
      return cors(json({ error: "only GET is supported" }, 405));
    }

    const url = new URL(request.url);
    const target = new URL(ARXIV_API);

    // Shorthand: ?q=… → search_query=all:…
    const q = url.searchParams.get("q");
    if (q) {
      target.searchParams.set("search_query", `all:${q}`);
    }
    // Native pass-through: any arxiv-recognised params
    for (const [k, v] of url.searchParams) {
      if (k === "q" || k === "max") continue;
      target.searchParams.set(k, v);
    }
    if (!target.searchParams.has("search_query")) {
      return cors(json({ error: "provide q=<terms> or search_query=<expr>" }, 400));
    }

    // Clamp max_results
    const max = Math.min(
      MAX_RESULTS_CAP,
      Number(url.searchParams.get("max") || target.searchParams.get("max_results") || 15),
    );
    target.searchParams.set("max_results", String(max));

    let upstream;
    try {
      upstream = await fetch(target.toString(), {
        cf: { cacheTtl: CACHE_TTL_SECONDS, cacheEverything: true },
      });
    } catch (err) {
      return cors(json({ error: `upstream fetch failed: ${err.message}` }, 502));
    }

    const body = await upstream.text();
    return cors(
      new Response(body, {
        status: upstream.status,
        headers: {
          "content-type":
            upstream.headers.get("content-type") || "application/atom+xml; charset=utf-8",
          "cache-control": `public, max-age=${CACHE_TTL_SECONDS}`,
        },
      }),
    );
  },
};

function cors(response) {
  const h = new Headers(response.headers);
  h.set("access-control-allow-origin", "*");
  h.set("access-control-allow-methods", "GET, OPTIONS");
  h.set("access-control-allow-headers", "content-type");
  h.set("access-control-max-age", "86400");
  return new Response(response.body, { status: response.status, headers: h });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
