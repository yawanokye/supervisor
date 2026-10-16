/* Shared, local-time readiness and scholarly reading-list display. */
window.VProfExtras = {
  time(value) {
    if (!value) return "";
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  },
  estimate(job, target) {
    if (!target) return;
    const until = this.time(job.estimated_ready_until);
    const from = this.time(job.estimated_ready_from);
    const back = this.time(job.check_back_at);
    target.textContent = until ? `Estimated ready: ${from} to ${until}. Suggested check-back: ${back}. ${job.estimate_note || "Estimates update as work progresses."}` : "";
  },
  readings(packet, target) {
    if (!target) return;
    target.replaceChildren();
    target.classList.toggle("hidden", !packet);
    if (!packet) return;
    const add = (tag, text, parent = target) => { const item = document.createElement(tag); item.textContent = text; parent.append(item); return item; };
    add("h3", "Related works and suggested readings");
    add("p", `Search: ${packet.title || ""}. Keywords: ${(packet.keywords || []).join(", ")}.`);
    add("p", (packet.source_status || []).map(s => `${s.source.replaceAll("_", " ")}: ${s.status}`).join(" · "));
    add("p", packet.scope || "Bibliographic suggestions require reading and verification.");
    for (const group of [{ title: "Suggested readings", rows: packet.suggested_readings || [] }, { title: "Related works already cited", rows: (packet.works || []).filter(w => w.already_cited) }]) {
      add("h4", group.title);
      if (!group.rows.length) add("p", "No matching works returned in this search.");
      const list = add("ol", "");
      for (const work of group.rows) {
        const li = add("li", "", list);
        const link = add("a", work.title, li);
        if (/^https?:\/\//i.test(work.url || "")) { link.href = work.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
        add("p", `${(work.authors || []).join(", ")} (${work.year || "year unavailable"}). ${work.venue || ""}`, li);
        add("p", `${work.reason || ""} Sources: ${(work.sources || []).join(", ")}.`, li);
        if (/^https?:\/\//i.test(work.open_access_url || "")) { const oa = add("a", "Open-access copy", li); oa.href = work.open_access_url; oa.target = "_blank"; oa.rel = "noopener noreferrer"; }
      }
    }
  }
};
document.querySelectorAll("[data-ready-time]").forEach(el => { el.textContent = window.VProfExtras.time(el.dataset.readyTime); });
