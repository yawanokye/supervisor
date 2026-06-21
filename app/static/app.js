const form = document.getElementById("reviewForm");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const emptyState = document.getElementById("emptyState");
const loadingState = document.getElementById("loadingState");
const resultsState = document.getElementById("resultsState");
const submitButton = document.getElementById("submitButton");
const chapterField = document.getElementById("chapterField");
const statusFilter = document.getElementById("statusFilter");
const showAllButton = document.getElementById("showAllButton");

let currentReview = null;
let showAll = false;

fileInput.addEventListener("change", () => {
  fileName.textContent = fileInput.files[0]?.name || "No file selected";
});

document.querySelectorAll('input[name="review_scope"]').forEach(input => {
  input.addEventListener("change", () => {
    chapterField.classList.toggle("hidden", input.value === "full_thesis" && input.checked);
  });
});

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));
}

function metric(label, value) {
  return `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
}

function evidenceHtml(item) {
  const evidence = item.evidence || [];
  if (!evidence.length) return "";
  return evidence.slice(0, 2).map(e => {
    const loc = [
      e.heading,
      e.page != null ? `page ${e.page}` : "",
      e.paragraph != null ? `paragraph ${e.paragraph}` : ""
    ].filter(Boolean).join(", ");
    return `<div class="evidence"><small>${escapeHtml(loc || "Evidence location")}</small>${escapeHtml(e.text)}</div>`;
  }).join("");
}

function findingHtml(item) {
  return `
    <article class="finding" data-status="${escapeHtml(item.status)}">
      <button class="finding-summary" type="button">
        <span class="code">${escapeHtml(item.code)}</span>
        <span class="criterion">${escapeHtml(item.item)}</span>
        <span class="status-pill status-${escapeHtml(item.status)}">${escapeHtml(item.status_label)}</span>
      </button>
      <div class="finding-body hidden">
        <p><span class="label">Section:</span> ${escapeHtml(item.section)}</p>
        <p><span class="label">Priority:</span> ${escapeHtml(item.severity)}</p>
        <p><span class="label">Expert assessment:</span> ${escapeHtml(item.comment)}</p>
        <p><span class="label">Required action:</span> ${escapeHtml(item.required_action)}</p>
        ${evidenceHtml(item)}
      </div>
    </article>`;
}

function bindFindings() {
  document.querySelectorAll(".finding-summary").forEach(btn => {
    btn.addEventListener("click", () => {
      btn.nextElementSibling.classList.toggle("hidden");
    });
  });
}

function applyFilter() {
  if (!currentReview) return;
  const filter = statusFilter.value;
  const rows = currentReview.results.filter(row => filter === "all" || row.status === filter);
  const limited = showAll ? rows : rows.slice(0, 20);
  document.getElementById("findingList").innerHTML =
    limited.map(findingHtml).join("") ||
    `<p class="form-note">No findings match this filter.</p>`;
  showAllButton.textContent = showAll ? "Show first 20" : `Show all criteria (${rows.length})`;
  bindFindings();
}

function renderReview(review) {
  currentReview = review;
  const s = review.summary;
  document.getElementById("resultTitle").textContent = s.filename;
  document.getElementById("overallScore").textContent = `${s.overall_score}%`;
  document.getElementById("readinessLabel").textContent = s.readiness_label;
  document.getElementById("readinessMeaning").textContent = s.readiness_meaning;
  document.getElementById("metrics").innerHTML = [
    metric("Meets", s.meets),
    metric("Partly meets", s.partial),
    metric("Does not meet", s.missing),
    metric("Manual review", s.manual),
    metric("Critical unresolved", s.critical_failed),
  ].join("");

  document.getElementById("priorityActions").innerHTML =
    (review.priority_actions || []).map(action => `
      <article class="action-item ${escapeHtml(action.severity)}">
        <strong>${escapeHtml(action.code)}</strong>
        <span>${escapeHtml(action.status)} · ${escapeHtml(action.severity)}</span>
        <p>${escapeHtml(action.action)}</p>
      </article>`).join("") ||
    `<p class="form-note">No priority actions were generated.</p>`;

  const annotatedButton = document.getElementById("annotatedButton");
  if (s.annotated_document_available) {
    annotatedButton.classList.remove("hidden");
    annotatedButton.disabled = false;
    annotatedButton.onclick = () => {
      window.location.href = `/api/review/${encodeURIComponent(review.review_id)}/annotated.docx`;
    };
  } else {
    annotatedButton.classList.add("hidden");
  }

  document.getElementById("downloadButton").onclick = () => {
    window.location.href = `/api/review/${encodeURIComponent(review.review_id)}/export.docx`;
  };
  applyFilter();
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const oldError = document.querySelector(".error-banner");
  if (oldError) oldError.remove();

  emptyState.classList.add("hidden");
  resultsState.classList.add("hidden");
  loadingState.classList.remove("hidden");
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "Reviewing…";

  try {
    const body = new FormData(form);
    const response = await fetch("/api/review", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "The review could not be completed.");
    renderReview(payload);
    loadingState.classList.add("hidden");
    resultsState.classList.remove("hidden");
  } catch (error) {
    loadingState.classList.add("hidden");
    emptyState.classList.remove("hidden");
    const banner = document.createElement("div");
    banner.className = "error-banner";
    banner.textContent = error.message;
    document.querySelector(".result-panel").prepend(banner);
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Run expert review";
  }
});

statusFilter.addEventListener("change", applyFilter);
showAllButton.addEventListener("click", () => {
  showAll = !showAll;
  applyFilter();
});
