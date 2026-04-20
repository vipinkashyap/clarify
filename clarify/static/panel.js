// Clarify claim-detail side panel.
//
// Click a tinted claim span → panel slides in from the right with its
// type, hedging, evidence, dependencies, and plain-language rewrite.
// Click outside, hit Esc, or press the × to close.
//
// This is the only non-KaTeX JavaScript Clarify runs on the reader page,
// and it does nothing until the reader interacts with a claim.

(() => {
  const dataEl = document.getElementById("claims-data");
  const panel = document.getElementById("panel");
  if (!dataEl || !panel) return;

  let claims = {};
  try {
    claims = JSON.parse(dataEl.textContent);
  } catch (err) {
    console.error("Clarify: could not parse claims-data", err);
    return;
  }

  const body = panel.querySelector(".panel-body");
  const closeBtn = panel.querySelector(".close");
  const mainEl = document.querySelector("main");

  const TYPE_LABELS = {
    empirical_result: "Empirical result",
    methodological_claim: "Methodological claim",
    theoretical_claim: "Theoretical claim",
    background_claim: "Background claim",
    limitation: "Limitation",
  };
  const HEDGE_LABELS = {
    asserted: "Asserted",
    suggested: "Suggested",
    speculated: "Speculated",
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderDeps(deps) {
    if (!deps || !deps.length) return "";
    const items = deps.map((id) => {
      if (claims[id]) {
        // Prefer the plain-language preview so the dep list reads
        // like a little reading list, not a technical citation index.
        const text = claims[id].plain_language || claims[id].statement;
        const preview = text.slice(0, 110) + (text.length > 110 ? "…" : "");
        return `<li><a href="#claim-${encodeURIComponent(id)}" class="dep-link" data-dep="${escapeHtml(id)}">${escapeHtml(preview)}</a></li>`;
      }
      return `<li><span class="dep-external">${escapeHtml(id)}</span></li>`;
    });
    return `<section class="panel-section panel-deps">
      <h3>What this builds on</h3>
      <ul>${items.join("")}</ul>
    </section>`;
  }

  function renderPanel(claim) {
    const typeLabel = TYPE_LABELS[claim.type] || claim.type;
    const hedgeLabel = HEDGE_LABELS[claim.hedging] || claim.hedging;

    // The plain version is the hero — it reads first, in a warmer serif,
    // so a non-expert arriving at this claim gets the meaning immediately.
    const hero = claim.plain_language
      ? `<section class="panel-section panel-hero">
           <h3>The short version</h3>
           <p>${escapeHtml(claim.plain_language)}</p>
         </section>`
      : `<section class="panel-section panel-hero">
           <h3>What the paper says</h3>
           <p>${escapeHtml(claim.statement)}</p>
         </section>`;

    // Verbatim statement — shown only if we also have a plain version.
    // Framed as a quote ("In the paper") so it's inviting rather than a wall.
    const quote = claim.plain_language
      ? `<section class="panel-section panel-quote">
           <h3>In the paper</h3>
           <blockquote>${escapeHtml(claim.statement)}</blockquote>
         </section>`
      : "";

    const evidence = claim.evidence
      ? `<section class="panel-section panel-evidence">
           <h3>Where to look</h3>
           <p>${escapeHtml(claim.evidence)}</p>
         </section>`
      : "";

    body.innerHTML = `
      <div class="panel-head">
        <span class="panel-badge claim-${escapeHtml(claim.type)}">${escapeHtml(typeLabel)}</span>
        <span class="panel-hedge">${escapeHtml(hedgeLabel)}</span>
      </div>
      ${hero}
      ${quote}
      ${evidence}
      ${renderDeps(claim.dependencies)}
      <div class="panel-foot">
        <span class="panel-cite">from <em>${escapeHtml(claim.section)}</em></span>
        <code>${escapeHtml(claim.id)}</code>
      </div>
    `;
  }

  function openPanel(claim, clickedEl) {
    renderPanel(claim);
    panel.hidden = false;
    document.body.classList.add("panel-open");
    // mark the active claim so the tint persists while the panel is open
    document.querySelectorAll(".claim.is-active").forEach((n) =>
      n.classList.remove("is-active"),
    );
    if (clickedEl) clickedEl.classList.add("is-active");
  }

  function closePanel() {
    panel.hidden = true;
    document.body.classList.remove("panel-open");
    document.querySelectorAll(".claim.is-active").forEach((n) =>
      n.classList.remove("is-active"),
    );
  }

  // Clicks on claim spans open the panel.
  mainEl.addEventListener("click", (ev) => {
    const el = ev.target.closest(".claim");
    if (!el) return;
    ev.preventDefault();
    const id = el.dataset.claimId;
    if (id && claims[id]) openPanel(claims[id], el);
  });

  // Keyboard support for focused claims.
  mainEl.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const el = ev.target.closest(".claim");
    if (!el) return;
    ev.preventDefault();
    const id = el.dataset.claimId;
    if (id && claims[id]) openPanel(claims[id], el);
  });

  // Dep-link clicks inside the panel jump to the referenced claim.
  body.addEventListener("click", (ev) => {
    const link = ev.target.closest(".dep-link");
    if (!link) return;
    ev.preventDefault();
    const depId = link.dataset.dep;
    const target = document.getElementById(`claim-${depId}`);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    if (claims[depId]) openPanel(claims[depId], target);
  });

  closeBtn.addEventListener("click", closePanel);

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !panel.hidden) closePanel();
  });

  // Click anywhere outside the panel or a claim closes it.
  document.addEventListener("click", (ev) => {
    if (panel.hidden) return;
    if (panel.contains(ev.target)) return;
    if (ev.target.closest(".claim")) return;
    closePanel();
  });
})();
