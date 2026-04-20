// Figure click-to-enlarge lightbox.
//
// Any <img> inside <main> can be clicked to open a full-bleed overlay
// with the image at natural size. Click the overlay, hit Esc, or click
// the × to close. One overlay element is built lazily on first open.

(() => {
  const main = document.querySelector("main");
  if (!main) return;

  let overlay = null;
  let img = null;
  let caption = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "figure");
    overlay.hidden = true;
    overlay.innerHTML = `
      <button class="lightbox-close" type="button" aria-label="close">×</button>
      <figure>
        <img alt="">
        <figcaption></figcaption>
      </figure>
    `;
    document.body.appendChild(overlay);
    img = overlay.querySelector("img");
    caption = overlay.querySelector("figcaption");
    overlay.addEventListener("click", (ev) => {
      if (ev.target.closest(".lightbox-close") || ev.target === overlay) {
        close();
      }
    });
    return overlay;
  }

  function open(src, alt, captionText) {
    ensureOverlay();
    img.src = src;
    img.alt = alt || "";
    caption.textContent = captionText || "";
    caption.hidden = !captionText;
    overlay.hidden = false;
    document.body.classList.add("lightbox-open");
  }

  function close() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.classList.remove("lightbox-open");
    // Clear src so the image doesn't stay in memory.
    if (img) img.src = "";
  }

  main.addEventListener("click", (ev) => {
    const target = ev.target;
    if (target.tagName !== "IMG") return;
    // Don't trigger inside the side panel or header.
    if (!main.contains(target)) return;
    ev.preventDefault();
    const figure = target.closest("figure");
    const figcap = figure ? figure.querySelector("figcaption") : null;
    open(target.src, target.alt, figcap ? figcap.textContent.trim() : "");
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") close();
  });
})();
