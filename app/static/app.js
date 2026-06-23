const form = document.getElementById("reviewForm");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const previousFilesInput = document.getElementById("previousFilesInput");
const previousFileNames = document.getElementById("previousFileNames");
const supervisorCommentFilesInput = document.getElementById("supervisorCommentFilesInput");
const supervisorCommentFileNames = document.getElementById("supervisorCommentFileNames");
const supervisorCommentsText = document.getElementById("supervisorCommentsText");
const originalFileInput = document.getElementById("originalFileInput");
const originalFileName = document.getElementById("originalFileName");
const revisionReviewFields = document.getElementById("revisionReviewFields");
const emptyState = document.getElementById("emptyState");
const loadingState = document.getElementById("loadingState");
const resultsState = document.getElementById("resultsState");
const submitButton = document.getElementById("submitButton");
const chapterField = document.getElementById("chapterField");
const chapterSelect = document.getElementById("chapterSelect");
const documentTypeField = document.getElementById("documentTypeField");
const previousChaptersField = document.getElementById("previousChaptersField");
const previousUploadTitle = document.getElementById("previousUploadTitle");
const previousUploadHelp = document.getElementById("previousUploadHelp");
const mainUploadTitle = document.getElementById("mainUploadTitle");
const statusFilter = document.getElementById("statusFilter");
const showAllButton = document.getElementById("showAllButton");

let currentReview = null;
let showAll = false;
const academicLevelSelect = form.querySelector('select[name="academic_level"]');
const doctoralNote = document.getElementById("doctoralNote");
const reviewDepthHelp = document.getElementById("reviewDepthHelp");
const lightReviewNote = document.getElementById("lightReviewNote");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const loadingMessage = document.getElementById("loadingMessage");

function updateDepthGuidance() {
  const doctoral = ["Professional Doctorate", "PhD"].includes(academicLevelSelect.value);
  doctoralNote.classList.toggle("hidden", !doctoral);
  const depth = form.querySelector('input[name="review_depth"]:checked')?.value || "standard";
  lightReviewNote.classList.toggle("hidden", depth !== "light");
  if (depth === "light") {
    reviewDepthHelp.textContent = "Light review is a faster, concise screening for common research flaws and practical corrections.";
  } else if (depth === "advanced") {
    reviewDepthHelp.textContent = "Advanced review applies deeper scrutiny of theory, methodology, originality and contribution, and may take longer.";
  } else {
    reviewDepthHelp.textContent = "Standard review provides a thorough academic assessment and is suitable for bachelor’s, master’s and most chapter reviews.";
  }
}
academicLevelSelect.addEventListener("change", updateDepthGuidance);
form.querySelectorAll('input[name="review_depth"]').forEach(input => input.addEventListener("change", updateDepthGuidance));
updateDepthGuidance();

function selectedScope() {
  return document.querySelector('input[name="review_scope"]:checked')?.value || "chapter";
}

function selectedDocumentType() {
  return document.querySelector('input[name="document_type"]:checked')?.value || "chapter_one";
}

function selectedStage() {
  return document.querySelector('input[name="submission_stage"]:checked')?.value || "initial";
}

function updateUploadWorkflow() {
  const scope = selectedScope();
  const stage = selectedStage();
  const chapter = Number(chapterSelect.value || 0);
  const fullThesis = scope === "full_thesis";
  const revised = stage === "revised";

  chapterField.classList.toggle("hidden", fullThesis);
  chapterSelect.required = !fullThesis;
  chapterSelect.disabled = fullThesis;

  documentTypeField.classList.toggle("hidden", fullThesis || chapter !== 1);
  previousChaptersField.classList.toggle("hidden", fullThesis || chapter < 2);
  previousFilesInput.required = !fullThesis && chapter >= 2;
  previousFilesInput.disabled = fullThesis || chapter < 2;

  revisionReviewFields.classList.toggle("hidden", !revised);
  supervisorCommentFilesInput.disabled = !revised;
  supervisorCommentsText.disabled = !revised;
  originalFileInput.disabled = !revised;

  const prefix = revised ? "Choose the revised " : "Choose ";
  if (fullThesis) {
    mainUploadTitle.textContent = revised ? "Choose the revised complete thesis" : "Choose the complete thesis";
    return;
  }

  if (chapter === 1) {
    const proposal = selectedDocumentType() === "proposal";
    if (revised) {
      mainUploadTitle.textContent = proposal ? "Choose the revised research proposal" : "Choose the revised Chapter One";
    } else {
      mainUploadTitle.textContent = proposal ? "Choose the research proposal" : "Choose Chapter One";
    }
  } else if (chapter >= 2) {
    mainUploadTitle.textContent = `${prefix}Chapter ${chapter} for review`;
    const last = chapter - 1;
    previousUploadTitle.textContent = last === 1 ? "Upload Chapter One" : `Upload Chapters 1 to ${last}`;
    previousUploadHelp.textContent = last === 1
      ? "Upload Chapter One as a DOCX or PDF so the current chapter can be checked against the problem, objectives, questions, hypotheses, concepts, and variables."
      : `Upload Chapters 1 to ${last} as one composite DOCX/PDF or as separate files. These files are used to test alignment with Chapter ${chapter}.`;
  } else {
    mainUploadTitle.textContent = revised ? "Choose the revised chapter under review" : "Choose the chapter under review";
  }
}

function setFileNames(input, target, emptyText) {
  const names = Array.from(input.files || []).map(file => file.name);
  target.textContent = names.length ? names.join(" • ") : emptyText;
}

fileInput.addEventListener("change", () => {
  fileName.textContent = fileInput.files[0]?.name || "No file selected";
});

previousFilesInput.addEventListener("change", () => {
  setFileNames(previousFilesInput, previousFileNames, "No previous chapter selected");
});

supervisorCommentFilesInput.addEventListener("change", () => {
  setFileNames(supervisorCommentFilesInput, supervisorCommentFileNames, "No supervisor-comment file selected");
});

originalFileInput.addEventListener("change", () => {
  originalFileName.textContent = originalFileInput.files[0]?.name || "No original chapter selected";
});

document.querySelectorAll('input[name="review_scope"], input[name="document_type"], input[name="submission_stage"]').forEach(input => {
  input.addEventListener("change", updateUploadWorkflow);
});

chapterSelect.addEventListener("change", updateUploadWorkflow);

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
      e.source_filename,
      e.heading,
      e.page != null ? `page ${e.page}` : "",
      e.paragraph != null ? `paragraph ${e.paragraph}` : ""
    ].filter(Boolean).join(", ");
    return `<div class="evidence"><small>${escapeHtml(loc || "Evidence location")}</small>${escapeHtml(e.text)}</div>`;
  }).join("");
}

function alignmentDetailsHtml(item) {
  const details = item.alignment_details || {};
  const unmatched = details.unmatched || [];
  if (!unmatched.length) return "";
  return `
    <div class="alignment-details">
      <strong>Earlier items not clearly carried forward</strong>
      <ol>${unmatched.map(value => `<li>${escapeHtml(value)}</li>`).join("")}</ol>
    </div>`;
}

function revisionDetailsHtml(item) {
  if (item.review_type !== "supervisor_comment") return "";
  const details = item.revision_details || {};
  const values = [];
  if (details.current_match_score != null) values.push(`Revised evidence match: ${Math.round(details.current_match_score * 100)}%`);
  if (details.original_match_score != null) values.push(`Original evidence match: ${Math.round(details.original_match_score * 100)}%`);
  if (details.passage_similarity != null) values.push(`Original-to-revised similarity: ${Math.round(details.passage_similarity * 100)}%`);
  const source = item.supervisor_comment_source
    ? `<p><span class="label">Comment source:</span> ${escapeHtml(item.supervisor_comment_source)}</p>`
    : "";
  const comparison = values.length
    ? `<p><span class="label">Revision comparison:</span> ${escapeHtml(values.join(" · "))}</p>`
    : "";
  return source + comparison;
}


function categoryLabel(value) {
  return String(value || "Academic review").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function findingHtml(item) {
  const category = item.review_type === "supervisor_comment"
    ? "Supervisor Follow-up"
    : item.review_type === "alignment"
      ? "Cross-Chapter Alignment"
      : categoryLabel(item.category);
  return `
    <article class="finding" data-status="${escapeHtml(item.status)}" data-severity="${escapeHtml(item.severity)}">
      <button class="finding-summary" type="button">
        <span class="code category-tag">${escapeHtml(category)}</span>
        <span class="criterion">${escapeHtml(item.item)}</span>
        <span class="status-pill status-${escapeHtml(item.status)}">${escapeHtml(item.status_label)}</span>
      </button>
      <div class="finding-body hidden">
        <p><span class="label">Section:</span> ${escapeHtml(item.section)}</p>
        <p><span class="label">Priority:</span> ${escapeHtml(item.severity)}</p>
        ${revisionDetailsHtml(item)}
        <p><span class="label">Academic assessment:</span> ${escapeHtml(item.comment)}</p>
        <p><span class="label">Required revision:</span> ${escapeHtml(item.required_action)}</p>
        ${item.illustrative_guidance ? `<p><span class="label">Illustrative guidance:</span> <em>${escapeHtml(item.illustrative_guidance)}</em></p>` : ""}
        ${alignmentDetailsHtml(item)}
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
  const rows = (currentReview.academic_findings || []).filter(row => filter === "all" || row.severity === filter);
  const limited = showAll ? rows : rows.slice(0, 20);
  document.getElementById("findingList").innerHTML =
    limited.map(findingHtml).join("") ||
    `<p class="form-note">No academic findings match this filter.</p>`;
  showAllButton.textContent = showAll ? "Show first 20" : `Show all findings (${rows.length})`;
  bindFindings();
}

function renderContextSummary(review) {
  const documents = review.context_documents || [];
  if (!documents.length) return "";
  return documents.map(doc => {
    const chapters = (doc.detected_chapters || []).length
      ? `Detected chapter(s): ${doc.detected_chapters.join(", ")}`
      : "Chapter labels need manual confirmation";
    return `<div class="context-file"><strong>${escapeHtml(doc.filename)}</strong><span>${escapeHtml(chapters)}</span></div>`;
  }).join("");
}

function renderRevisionSourceSummary(review) {
  const sources = review.supervisor_comment_sources || [];
  const original = review.original_document;
  const sourceRows = sources.map(source =>
    `<div class="context-file"><strong>${escapeHtml(source)}</strong><span>Supervisor comments</span></div>`
  );
  if (original) {
    sourceRows.push(`<div class="context-file"><strong>${escapeHtml(original.filename)}</strong><span>Original version used for comparison</span></div>`);
  }
  return sourceRows.join("");
}

function renderReview(review) {
  currentReview = review;
  const s = review.summary;
  document.getElementById("resultTitle").textContent = `${s.document_label}: ${s.filename}`;
  document.getElementById("overallScore").textContent = `${s.overall_score}%`;
  document.getElementById("readinessLabel").textContent = s.readiness_label;
  document.getElementById("readinessMeaning").textContent = s.readiness_meaning;

  const metricRows = [
    metric("Academic review", `${s.academic_review_score}%`),
    metric("Alignment", s.alignment_score == null ? "N/A" : `${s.alignment_score}%`),
    metric("Critical issues", s.critical_issues || 0),
    metric("Major issues", s.major_issues || 0),
    metric("Moderate issues", s.moderate_issues || 0),
    metric("Strengths", s.strengths_identified || 0),
  ];
  if (s.revised_mode) {
    metricRows.splice(2, 0, metric("Comment compliance", s.revision_score == null ? "Manual" : `${s.revision_score}%`));
  }
  document.getElementById("metrics").innerHTML = metricRows.join("");

  const strengths = review.academic_strengths || [];
  const strengthsSection = document.getElementById("strengthsSection");
  strengthsSection.classList.toggle("hidden", !strengths.length);
  if (strengths.length) {
    document.getElementById("strengthsList").innerHTML = strengths.slice(0, 12).map(item => `
      <article class="action-item strength">
        <strong>${escapeHtml(item.section || "Chapter")}</strong>
        <p>${escapeHtml(item.observation)}</p>
      </article>`).join("");
  }

  document.getElementById("priorityActions").innerHTML =
    (review.priority_actions || []).map(action => `
      <article class="action-item ${escapeHtml(action.severity)}">
        <strong>${escapeHtml(action.issue || action.section || "Academic revision")}</strong>
        <span>${escapeHtml(action.status)} · ${escapeHtml(action.severity)}</span>
        <p>${escapeHtml(action.action)}</p>
      </article>`).join("") ||
    `<p class="form-note">No priority actions were generated.</p>`;

  const revisionRows = review.revision_results || [];
  const revisionSection = document.getElementById("revisionSection");
  revisionSection.classList.toggle("hidden", !revisionRows.length);
  if (revisionRows.length) {
    document.getElementById("revisionScore").textContent = s.revision_score == null ? "Manual review" : `${s.revision_score}%`;
    document.getElementById("revisionSourceSummary").innerHTML = renderRevisionSourceSummary(review);
    document.getElementById("revisionList").innerHTML = revisionRows.map(findingHtml).join("");
  }

  const alignmentRows = review.alignment_results || [];
  const alignmentSection = document.getElementById("alignmentSection");
  alignmentSection.classList.toggle("hidden", !alignmentRows.length);
  if (alignmentRows.length) {
    document.getElementById("alignmentScore").textContent = s.alignment_score == null ? "Manual review" : `${s.alignment_score}%`;
    document.getElementById("contextSummary").innerHTML = renderContextSummary(review);
    document.getElementById("alignmentList").innerHTML = alignmentRows.map(findingHtml).join("");
  }

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
  bindFindings();
}

function showFormError(message, target = null) {
  const oldError = document.querySelector(".error-banner");
  if (oldError) oldError.remove();
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.textContent = message;
  document.querySelector(".result-panel").prepend(banner);
  if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function readJsonSafely(response) {
  const text = await response.text();
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  let payload = null;
  if (contentType.includes("application/json")) {
    try { payload = JSON.parse(text); } catch (_) { payload = null; }
  }
  if (!payload && text.trim().startsWith("{")) {
    try { payload = JSON.parse(text); } catch (_) { payload = null; }
  }
  if (!payload) {
    if (text.trim().startsWith("<")) {
      throw new Error("The server returned a temporary web-service error instead of review data. Please retry. Your document was not processed as a valid review response.");
    }
    throw new Error(response.ok ? "The server returned an unreadable response." : `The review service returned error ${response.status}.`);
  }
  if (!response.ok) throw new Error(payload.detail || payload.error || "The review could not be completed.");
  return payload;
}

function updateProgress(job) {
  const value = Math.max(2, Math.min(100, Number(job.progress || 2)));
  progressBar.style.width = `${value}%`;
  progressText.textContent = `${value}%`;
  loadingMessage.textContent = job.message || "Reviewing the document";
}

async function waitForReview(pollUrl) {
  const started = Date.now();
  let temporaryFailures = 0;
  while (Date.now() - started < 30 * 60 * 1000) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    try {
      const response = await fetch(pollUrl, { headers: { "Accept": "application/json" } });
      const job = await readJsonSafely(response);
      temporaryFailures = 0;
      updateProgress(job);
      if (job.status === "completed") return job.review;
      if (job.status === "failed") throw new Error(job.error || "The review could not be completed.");
    } catch (error) {
      temporaryFailures += 1;
      if (temporaryFailures >= 5) throw error;
      loadingMessage.textContent = "The connection was interrupted. Reconnecting to the review job…";
    }
  }
  throw new Error("The review is still taking longer than expected. Please retry or check the service status.");
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const oldError = document.querySelector(".error-banner");
  if (oldError) oldError.remove();

  const scope = selectedScope();
  const stage = selectedStage();
  const chapter = Number(chapterSelect.value || 0);
  if (scope === "chapter" && !chapter) { chapterSelect.focus(); return; }
  if (scope === "chapter" && chapter >= 2 && !(previousFilesInput.files || []).length) {
    showFormError(`Upload Chapters 1 to ${chapter - 1} as one composite file or as separate files before running the review.`, previousChaptersField); return;
  }
  if (stage === "revised" && !(supervisorCommentFilesInput.files || []).length && !supervisorCommentsText.value.trim()) {
    showFormError("Upload the supervisor comments or paste them into the comments box before reviewing a revised chapter.", revisionReviewFields); return;
  }

  emptyState.classList.add("hidden"); resultsState.classList.add("hidden"); loadingState.classList.remove("hidden");
  progressBar.style.width = "2%"; progressText.textContent = "2%"; loadingMessage.textContent = "Uploading and queuing the review";
  submitButton.disabled = true; submitButton.querySelector("span").textContent = "Review in progress…";

  try {
    const body = new FormData(form);
    if (scope === "full_thesis") { body.set("selected_chapter", "0"); body.set("document_type", "full_thesis"); body.delete("previous_files"); }
    if (stage !== "revised") { body.delete("supervisor_comment_files"); body.delete("supervisor_comments_text"); body.delete("original_file"); }
    const response = await fetch("/api/review", { method: "POST", body, headers: { "Accept": "application/json" } });
    const queued = await readJsonSafely(response);
    updateProgress(queued);
    const review = await waitForReview(queued.poll_url);
    renderReview(review);
    loadingState.classList.add("hidden"); resultsState.classList.remove("hidden");
  } catch (error) {
    loadingState.classList.add("hidden"); emptyState.classList.remove("hidden"); showFormError(error.message);
  } finally {
    submitButton.disabled = false; submitButton.querySelector("span").textContent = "Run expert review";
  }
});

statusFilter.addEventListener("change", applyFilter);
showAllButton.addEventListener("click", () => {
  showAll = !showAll;
  applyFilter();
});

updateUploadWorkflow();
