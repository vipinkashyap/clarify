// Evening 1 stub reader. Renders a cached paper end-to-end; full annotation
// overlay and side panel behavior land in Evening 5.

const pathParts = window.location.pathname.split("/");
const arxivId = decodeURIComponent(pathParts[pathParts.length - 1]);

const main = document.getElementById("paper");
const headerTitle = document.getElementById("header-title");

async function load() {
  let res;
  try {
    res = await fetch(`/api/papers/${encodeURIComponent(arxivId)}`);
  } catch (e) {
    showError(`Network error: ${e.message}`);
    return;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    showError(body.detail?.hint || `Paper ${arxivId} not found.`);
    return;
  }
  const paper = await res.json();
  render(paper);
}

function render(paper) {
  headerTitle.textContent = paper.title;
  document.title = `${paper.title} — Clarify`;

  const sectionsHtml = paper.sections.map(s => {
    const tag = `h${Math.min(Math.max(s.level, 2), 3)}`;
    return `<${tag}>${escapeHtml(s.title)}</${tag}>${s.html}`;
  }).join("");

  const claimsBySection = groupClaimsBySection(paper.claims);
  // TODO(evening-5): wrap character ranges in each section text with <span class="claim">.
  // For now, just render the raw HTML.

  main.innerHTML = `
    <h1>${escapeHtml(paper.title)}</h1>
    <div class="authors">${paper.authors.map(escapeHtml).join(", ")}</div>
    ${paper.abstract ? `<div class="abstract"><span class="label">Abstract</span>${escapeHtml(paper.abstract)}</div>` : ""}
    ${sectionsHtml}
  `;

  // Re-run KaTeX on the newly-inserted content.
  if (window.renderMathInElement) {
    window.renderMathInElement(main, {
      throwOnError: false,
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
    });
  }

  // Log claim counts so we can tell at a glance whether the paper has been
  // extracted yet.
  console.info(`Loaded ${paper.arxiv_id}: ${paper.claims.length} claims across ${paper.sections.length} sections.`);
  if (paper.claims.length === 0) {
    console.info(`No claims ingested yet for ${paper.arxiv_id}. Follow clarify/prompts/extract_claims.md.`);
  }
}

function groupClaimsBySection(claims) {
  const g = new Map();
  for (const c of claims) {
    if (!g.has(c.section)) g.set(c.section, []);
    g.get(c.section).push(c);
  }
  return g;
}

function showError(message) {
  main.innerHTML = `<div class="error"><p>${escapeHtml(message)}</p></div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Toggle stub — does nothing yet; wired fully in Evening 5.
for (const btn of document.querySelectorAll(".toggle button")) {
  btn.addEventListener("click", () => {
    for (const b of document.querySelectorAll(".toggle button")) {
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    }
  });
}

load();
