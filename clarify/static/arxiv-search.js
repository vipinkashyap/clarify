// Live arxiv search.
//
// Activated only when <meta name="clarify-worker" content="…"> is present.
// If absent, this script is a no-op and the gallery falls back to the
// pre-fetched Discover section.
//
// Hooks into the existing #search input: filters local (extracted) cards
// while typing, and after a debounce, queries the Cloudflare Worker for
// arxiv results matching the same query. Results land in a new section
// above the pre-fetched Discover content.

(() => {
  const meta = document.querySelector('meta[name="clarify-worker"]');
  const workerUrl = meta?.content?.trim();
  if (!workerUrl) return; // Live search disabled.

  const input = document.getElementById("search");
  const discoverSection = document.querySelector(".discover");
  if (!input || !discoverSection) return;

  const REPO = "vipinkashyap/clarify";
  const DEBOUNCE_MS = 450;
  const MIN_CHARS = 3;

  // Ingested arxiv ids — used to mark live results that are already in the cache.
  const ingested = new Set(
    [...document.querySelectorAll(".paper-card")]
      .map((c) => c.dataset.search?.split(" ")[0])
      .filter(Boolean),
  );

  // Container for live results, inserted above the pre-fetched Discover groups.
  const live = document.createElement("section");
  live.className = "live-search";
  live.hidden = true;
  live.innerHTML = `
    <h3 class="group-label">Arxiv search <span class="live-status" id="live-status"></span></h3>
    <div class="preview-grid" id="live-grid"></div>
  `;
  discoverSection.insertBefore(
    live,
    discoverSection.querySelector(".discover-groups"),
  );
  const grid = live.querySelector("#live-grid");
  const status = live.querySelector("#live-status");

  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
    );

  const normalizeId = (entryId) => {
    const last = entryId.split("/").pop() || entryId;
    return last.split("v")[0];
  };

  const requestUrl = (arxivId, title) => {
    const q = new URLSearchParams({
      template: "request-paper.md",
      title: `[Request] ${title}`,
      body: `**arxiv id:** ${arxivId}\n\n**Title:** ${title}\n\n**Why this matters** (1–2 sentences):`,
    });
    return `https://github.com/${REPO}/issues/new?${q.toString()}`;
  };

  const renderEntry = (e) => {
    const id = normalizeId(e.id || "");
    const title = (e.title || "").replace(/\s+/g, " ").trim();
    const authors = e.authors.slice(0, 3).join(", ");
    const more =
      e.authors.length > 3
        ? ` <span class="et-al">+${e.authors.length - 3}</span>`
        : "";
    const summary = (e.summary || "").replace(/\s+/g, " ").trim().slice(0, 260);
    const isIngested = ingested.has(id);
    const action = isIngested
      ? `<a class="card-cta" href="${
          onStaticSite() ? `p/${encodeURIComponent(id)}.html` : `/paper/${id}`
        }">Read →</a>`
      : `<a class="card-request" href="${requestUrl(id, title)}" target="_blank" rel="noopener">Request →</a>`;
    return `
      <div class="preview-card ${isIngested ? "is-ingested" : ""}">
        <div class="card-meta">
          <span class="card-id">${escapeHtml(id)}</span>
          ${e.category ? `<span class="card-cat">${escapeHtml(e.category)}</span>` : ""}
        </div>
        <h3 class="card-title">${escapeHtml(title)}</h3>
        <div class="card-authors">${escapeHtml(authors)}${more}</div>
        <p class="card-summary">${escapeHtml(summary)}${summary.length >= 260 ? "…" : ""}</p>
        <div class="card-foot">${action}</div>
      </div>
    `;
  };

  // Detect static (file-based) vs runtime server so paper links resolve correctly.
  function onStaticSite() {
    return !!document.querySelector('a[href^="p/"]');
  }

  function parseAtom(xml) {
    const doc = new DOMParser().parseFromString(xml, "application/xml");
    if (doc.querySelector("parsererror")) return [];
    return [...doc.querySelectorAll("entry")].map((el) => ({
      id: el.querySelector("id")?.textContent || "",
      title: el.querySelector("title")?.textContent || "",
      summary: el.querySelector("summary")?.textContent || "",
      authors: [...el.querySelectorAll("author > name")].map((n) => n.textContent || ""),
      category:
        el.querySelector("primary_category")?.getAttribute("term") ||
        el.querySelector("category")?.getAttribute("term") ||
        "",
    }));
  }

  let activeQuery = "";
  let debounceTimer = null;
  let inflight = null;

  async function runSearch(query) {
    status.textContent = "searching…";
    live.hidden = false;
    const url = new URL(workerUrl);
    url.searchParams.set("q", query);
    url.searchParams.set("max", "15");

    if (inflight) inflight.abort();
    inflight = new AbortController();
    try {
      const r = await fetch(url, { signal: inflight.signal });
      if (!r.ok) {
        status.textContent = `search failed (${r.status})`;
        grid.innerHTML = "";
        return;
      }
      const xml = await r.text();
      const entries = parseAtom(xml);
      if (activeQuery !== query) return; // superseded
      if (!entries.length) {
        status.textContent = "no results";
        grid.innerHTML = "";
        return;
      }
      status.textContent = `${entries.length} result${entries.length === 1 ? "" : "s"}`;
      grid.innerHTML = entries.map(renderEntry).join("");
    } catch (err) {
      if (err.name === "AbortError") return;
      status.textContent = "search failed";
      grid.innerHTML = "";
    }
  }

  input.addEventListener("input", () => {
    const q = input.value.trim();
    activeQuery = q;
    clearTimeout(debounceTimer);
    if (q.length < MIN_CHARS) {
      live.hidden = true;
      grid.innerHTML = "";
      status.textContent = "";
      if (inflight) inflight.abort();
      return;
    }
    debounceTimer = setTimeout(() => runSearch(q), DEBOUNCE_MS);
  });
})();
