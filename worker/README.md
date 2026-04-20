# Clarify arxiv Worker

A ~60-line Cloudflare Worker that proxies requests to `export.arxiv.org/api/query`, adds the CORS headers arxiv doesn't send, and caches responses briefly. Lets Clarify's gallery do live browser-side arxiv search without running a backend.

## Deploy

You need a Cloudflare account and `wrangler` installed.

```bash
npm install -g wrangler
wrangler login
cd worker
wrangler deploy
```

First deploy assigns a URL like `https://clarify-arxiv.<your-subdomain>.workers.dev`. Copy it.

## Wire it into the site

Set the Worker URL as a **repository variable** (not a secret — it's a public URL):

1. GitHub → repo → **Settings → Secrets and variables → Actions → Variables → New repository variable**
2. Name: `CLARIFY_WORKER_URL`
3. Value: `https://clarify-arxiv.<your-subdomain>.workers.dev`

The next push to `main` picks it up: the deploy workflow reads `CLARIFY_WORKER_URL` and renders a meta tag the gallery JS uses to enable live search.

If the variable isn't set, live search silently stays off — the gallery still shows the pre-fetched Discover section, and every other feature works.

## Try it

```bash
curl 'https://clarify-arxiv.<your-subdomain>.workers.dev/?q=attention+is+all+you+need&max=3'
```

You should get back Atom XML, `access-control-allow-origin: *`, and a `cache-control: public, max-age=300` header.

## Costs

Cloudflare's free tier is 100,000 requests per day. A user landing, typing a few queries, and clicking a paper is roughly 3–5 requests. That's 20k+ unique users/day before the free tier runs out. For this prototype it's effectively free.

## Local dev

```bash
wrangler dev    # runs the Worker on localhost:8787
```

Then point `CLARIFY_WORKER_URL` at `http://localhost:8787` in your environment while running `uvicorn clarify.main:app --reload`:

```bash
CLARIFY_WORKER_URL=http://localhost:8787 uv run uvicorn clarify.main:app --reload
```

## Security notes

The proxy is open to the world by default — any origin can hit it. For a prototype that's fine. To restrict to only your site's origin, uncomment the `ALLOWED_ORIGIN` check in `src/index.js` and set it via `wrangler secret put ALLOWED_ORIGIN`.
