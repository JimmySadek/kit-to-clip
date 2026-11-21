/* Registry text is data. External previews open only through explicit links. No build starts here. */
(() => {
  const data = window.KIT_GALLERY;
  const grid = document.getElementById("grid");
  const notice = document.getElementById("notice");
  const fallback = document.getElementById("copy-fallback");
  const requestText = document.getElementById("request-text");
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const button = (text, action, className) => {
    const el = node("button", text, className);
    el.type = "button";
    el.addEventListener("click", action);
    return el;
  };
  document.getElementById("brand").textContent = data.brand ? "Request brand: " + data.brand : "Branding is optional. Choose a style first.";
  const search = document.getElementById("search");
  search.value = data.query || "";
  const family = document.getElementById("family");
  const more = document.getElementById("more");
  const all = document.getElementById("all");
  let category = data.items.some(item => item.category === "library") ? "library" : "legacy";
  let visible = 15;
  let copyOrigin;
  document.getElementById("close-copy").addEventListener("click", () => {
    fallback.hidden = true;
    if (copyOrigin) copyOrigin.focus();
  });
  const copyRequest = async (item, origin) => {
    const draft = item.category === "saved" && item.status !== "approved";
    let text = item.category === "new" ? "Help me create a new video direction from my idea or references." :
      draft ? `Continue developing my saved style ${item.name} (${item.style}). It is still a draft.` :
      item.category === "library" ? `Rebuild the Atlas reference ${item.name} (${item.id}) for my story. Load only its selected original prompt/code from my private collection and preserve its medium and motion.` :
      item.category === "looks" ? `Make an explainer using the ${item.name} style (${item.style}).` :
      item.category === "saved" ? `Make a video using my saved style ${item.name} (${item.style}).` :
      `Make a video using the ${item.name} format (${item.format}).`;
    text += data.brand ? ` Adapt it with the ${data.brand} brand kit while preserving the style.` :
      " Help me decide whether to keep the original look or adapt its branding. Do not automatically reuse a previous brand.";
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(text);
      notice.textContent = "Request copied. Paste it into your chat.";
      fallback.hidden = true;
    } catch {
      copyOrigin = origin;
      requestText.value = text;
      fallback.hidden = false;
      notice.textContent = "Copy this request and paste it into your chat.";
      requestText.focus();
      requestText.select();
    }
  };
  const inCategory = item => category === "legacy" ? ["looks", "formats"].includes(item.category) : item.category === category;
  const terms = () => search.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const match = item => {
    const title = item.name.toLocaleLowerCase();
    const metadata = [item.family, item.about, ...(item.tags || [])].join(" ").toLocaleLowerCase();
    const matched = terms().filter(term => title.includes(term) || metadata.includes(term));
    return { matched, weight: matched.reduce((sum, term) => sum + (title.includes(term) ? 4 : 1), 0) };
  };
  const show = () => {
    grid.querySelectorAll("video").forEach(video => video.pause());
    grid.replaceChildren();
    fallback.hidden = true;
    notice.textContent = "";
    document.getElementById("category").value = category;
    document.querySelectorAll("[data-category]").forEach(el =>
      el.setAttribute("aria-pressed", String(el.dataset.category === category)));
    const candidates = data.items.filter(item => inCategory(item) && (!family.value || item.family === family.value));
    const items = candidates.map((item, order) => ({item, order, ...match(item)}))
      .filter(row => !terms().length || row.matched.length)
      .sort((a, b) => b.weight - a.weight || a.order - b.order);
    document.getElementById("results").textContent = `Showing ${Math.min(visible, items.length)} of ${items.length} matches` +
      (terms().length ? ". Keyword matches are suggestions to discuss, not tested suitability." : ". Browse more or narrow by a look or topic.");
    more.hidden = all.hidden = visible >= items.length;
    document.getElementById("collection-note").textContent = category === "library" ?
      "86 Atlas references. Original previews open on request. Rebuilding needs your local source collection; these references have not all been rendered or approved in Kit to Clip." :
      category === "saved" ? "Your saved treatments, including drafts. A previous brand is context, not a choice for this video." :
      "Older Kit to Clip formats and simplified explainer looks. These remain available and are separate from the Atlas references.";
    if (!items.length) {
      grid.append(node("p", category === "saved" && !search.value && !family.value ?
        "No saved styles yet. After an approved video, you can save its treatment here." :
        "No matches. Try fewer words, another family or a new direction.", "empty"));
    }
    for (const {item, matched} of items.slice(0, visible)) {
      const card = node("article", undefined, "sample");
      const media = node("div", undefined, "media");
      const preview = item.preview;
      let video;
      if (preview?.video) {
        video = document.createElement("video");
        video.src = preview.video;
        video.controls = true;
        video.preload = "none";
        video.playsInline = true;
        video.setAttribute("aria-label", item.name + " sample");
        if (preview.poster) video.poster = preview.poster;
        video.addEventListener("play", () => grid.querySelectorAll("video").forEach(other => {
          if (other !== video) other.pause();
        }));
        video.addEventListener("error", () => { media.replaceChildren(node("p", "Sample unavailable. Ask to rebuild it.")); });
        media.append(video);
      } else if (preview?.poster) {
        const image = document.createElement("img");
        image.src = preview.poster;
        image.alt = item.name + " sample still";
        image.loading = "lazy";
        image.addEventListener("error", () => media.replaceChildren(node("p", "Sample unavailable. Ask to rebuild it.")));
        media.append(image);
      } else {
        if (item.category === "library") media.classList.add("external-only");
        media.append(node("p", item.preview_warning || (item.category === "library" ? "Original previews linked below" : "No sample yet")));
      }
      const status = item.status || "draft";
      const labels = item.category === "library" ?
        (preview ? [preview.label, "Local reference study", item.family] : ["Atlas reference", item.family]) :
        [preview?.label || "No sample yet", status.charAt(0).toUpperCase() + status.slice(1)];
      const originalBrand = item.brand || item.original_brand;
      if (originalBrand && originalBrand !== "any" && originalBrand !== data.brand) labels.push("Previously " + originalBrand);
      if (preview?.poster && !preview.video) labels.splice(1, 0, "Still preview");
      card.append(media, node("p", labels.join(" · "), "kind"), node("h2", item.name), node("p", item.about, "description"));
      if (matched.length) card.append(node("p", "Matches: " + matched.join(", "), "reason"));
      if (item.category === "library") {
        const details = node("details");
        details.append(node("summary", "Motion, fit and limits"));
        details.append(node("p", "Motion: " + (item.motion || []).join(", "), "constraints"));
        details.append(node("p", "Possible fit (inferred): " + (item.fit || []).join(", "), "constraints"));
        (item.limitations || []).forEach(text => details.append(node("p", text, "constraints")));
        card.append(details);
      }
      const actions = node("div", undefined, "actions");
      for (const [key, label] of [["style_frame_video", "Original style demo"], ["explainer_clip", "Original explainer"]]) {
        const url = item.original_previews?.[key];
        if (!url) continue;
        try {
          const parsed = new URL(url);
          if (parsed.protocol !== "https:") continue;
          const link = node("a", label);
          link.href = parsed.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          actions.append(link);
        } catch { /* Invalid metadata never becomes a navigable link. */ }
      }
      if (video) {
        const play = button("Play sample", () => {
          if (!video.paused) { video.pause(); return; }
          video.play().catch(() => { notice.textContent = "Use the sample's video controls to play it."; });
        });
        video.addEventListener("play", () => { play.textContent = "Pause sample"; });
        video.addEventListener("pause", () => { play.textContent = "Play sample"; });
        video.addEventListener("ended", () => { play.textContent = "Play sample"; });
        actions.append(play);
      }
      const copy = button("Copy request", () => copyRequest(item, copy), "copy");
      copy.disabled = Boolean(item.broken) || status === "retired";
      actions.append(copy);
      card.append(actions);
      grid.append(card);
    }
  };
  const selectCategory = value => {
    category = value;
    visible = 15;
    family.replaceChildren(node("option", "All families"));
    family.firstChild.value = "";
    [...new Set(data.items.filter(inCategory).map(item => item.family).filter(Boolean))].sort().forEach(name => {
      const option = node("option", name);
      option.value = name;
      family.append(option);
    });
    show();
  };
  document.querySelectorAll("[data-category]").forEach(el => el.addEventListener("click", () => selectCategory(el.dataset.category)));
  document.getElementById("category").addEventListener("change", event => selectCategory(event.target.value));
  search.addEventListener("input", () => { visible = 15; show(); });
  family.addEventListener("change", () => { visible = 15; show(); });
  more.addEventListener("click", () => { visible += 15; show(); });
  all.addEventListener("click", () => { visible = data.items.length; show(); });
  const newDirection = document.getElementById("new-direction");
  newDirection.addEventListener("click", () => copyRequest({category: "new"}, newDirection));
  selectCategory(category);
})();
