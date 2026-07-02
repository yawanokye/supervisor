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
const combinedChapterField = document.getElementById("combinedChapterField");
const combinedChapterEnd = document.getElementById("combinedChapterEnd");
const documentTypeField = document.getElementById("documentTypeField");
const previousChaptersField = document.getElementById("previousChaptersField");
const previousUploadTitle = document.getElementById("previousUploadTitle");
const previousUploadHelp = document.getElementById("previousUploadHelp");
const mainUploadTitle = document.getElementById("mainUploadTitle");
const statusFilter = document.getElementById("statusFilter");
const showAllButton = document.getElementById("showAllButton");

let currentReview = null;
let showAll = false;
const ACTIVE_REVIEW_JOB_KEY = "ai-professor-active-review-job";
const academicLevelSelect = form.querySelector('select[name="academic_level"]');
const doctoralNote = document.getElementById("doctoralNote");
const reviewDepthHelp = document.getElementById("reviewDepthHelp");
const lightReviewNote = document.getElementById("lightReviewNote");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const loadingMessage = document.getElementById("loadingMessage");
const scopeStructureHelp = document.getElementById("scopeStructureHelp");

function updateDepthGuidance() {
  const doctoral = ["Professional Doctorate", "PhD"].includes(academicLevelSelect.value);
  doctoralNote.classList.toggle("hidden", !doctoral);
  const depth = form.querySelector('input[name="review_depth"]:checked')?.value || "standard";
  lightReviewNote.classList.toggle("hidden", depth !== "light");
  if (depth === "light") {
    reviewDepthHelp.textContent = "Light Review examines every section and subsection at Bachelor’s or non-research Master’s level, with practical guidance and examples where needed.";
  } else if (depth === "advanced") {
    reviewDepthHelp.textContent = "Advanced Review examines every section and subsection at Professional Doctorate or PhD level, with rigorous scrutiny of originality, theory, methodology and contribution to knowledge.";
  } else {
    reviewDepthHelp.textContent = "Standard Review examines every section and subsection at Research Master’s or MPhil level, with stronger critical synthesis and methodological scrutiny.";
  }
}
academicLevelSelect.addEventListener("change", () => {
  updateDepthGuidance();
  updateUploadWorkflow();
});
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
  const rangeEnd = Number(combinedChapterEnd.value || 0);
  const combined = scope === "chapter_range";
  const fullThesis = scope === "full_thesis";
  const revised = stage === "revised";
  const doctoral = ["Professional Doctorate", "PhD"].includes(
    academicLevelSelect.value
  );

  if (scopeStructureHelp) {
    if (combined) {
      scopeStructureHelp.textContent =
        "Choose the last chapter in the range. The composite upload must contain every chapter in the selected range, beginning with Chapter One. All chapters in the range are reviewed together.";
    } else {
      scopeStructureHelp.textContent = doctoral
        ? "Professional Doctorate and PhD theses may use custom chapter numbers, order and titles. Complete-thesis review checks core research functions, integration and contribution rather than enforcing five chapters."
        : "Bachelor’s and Master’s complete theses are checked against the standard research structure, with justified additional chapters allowed.";
    }
  }

  chapterField.classList.toggle("hidden", fullThesis || combined);
  chapterSelect.required = !fullThesis && !combined;
  chapterSelect.disabled = fullThesis || combined;

  combinedChapterField.classList.toggle("hidden", !combined);
  combinedChapterEnd.required = combined;
  combinedChapterEnd.disabled = !combined;

  documentTypeField.classList.toggle(
    "hidden",
    fullThesis || combined || chapter !== 1
  );
  previousChaptersField.classList.toggle(
    "hidden",
    fullThesis || combined || chapter < 2
  );
  previousFilesInput.required = false;
  previousFilesInput.disabled = fullThesis || combined || chapter < 2;

  revisionReviewFields.classList.toggle("hidden", !revised);
  supervisorCommentFilesInput.disabled = !revised;
  supervisorCommentsText.disabled = !revised;
  originalFileInput.disabled = !revised;

  const prefix = revised ? "Choose the revised " : "Choose ";
  if (fullThesis) {
    if (doctoral) {
      mainUploadTitle.textContent = revised
        ? "Choose the revised complete doctoral thesis"
        : "Choose the complete doctoral thesis";
    } else {
      mainUploadTitle.textContent = revised
        ? "Choose the revised complete thesis"
        : "Choose the complete thesis";
    }
    return;
  }

  if (combined) {
    mainUploadTitle.textContent = rangeEnd
      ? `${revised ? "Choose the revised" : "Choose"} combined Chapters 1 to ${rangeEnd}`
      : `${revised ? "Choose the revised" : "Choose"} combined chapter document`;
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
      ? "If the main upload does not already contain Chapter One, upload it here for alignment. When the main file is composite, only the selected chapter is reviewed and Chapter One is used as context."
      : `If the main upload does not already contain Chapters 1 to ${last}, upload them here as one composite file or separate files. Other chapters are used for alignment only.`;
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
combinedChapterEnd.addEventListener("change", updateUploadWorkflow);

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

async function fetchCompletedReview(job) {
  if (job.review && typeof job.review === "object") return job.review;
  const resultUrl = job.result_url || (job.review_id ? `/api/review/${encodeURIComponent(job.review_id)}` : "");
  if (!resultUrl) throw new Error("The review finished, but the result location was not returned.");
  const response = await fetch(resultUrl, { headers: { "Accept": "application/json" } });
  return await readJsonSafely(response);
}

async function waitForReview(pollUrl, options = {}) {
  const started = Number(options.startedAt || Date.now());
  const maximumWait = 2 * 60 * 60 * 1000;
  let temporaryFailures = 0;
  let pollDelay = 2500;

  while (Date.now() - started < maximumWait) {
    await new Promise(resolve => setTimeout(resolve, pollDelay));
    try {
      const response = await fetch(pollUrl, {
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      if ([401, 403, 404].includes(response.status)) {
        let message = "The review job is no longer available.";
        try {
          const payload = await readJsonSafely(response);
          message = payload.detail || payload.error || message;
        } catch (_) {
          // Keep the clear terminal message above.
        }
        const terminalError = new Error(message);
        terminalError.terminal = true;
        throw terminalError;
      }

      const job = await readJsonSafely(response);
      temporaryFailures = 0;
      pollDelay = Date.now() - started > 30 * 60 * 1000 ? 10000 : 2500;
      updateProgress(job);

      localStorage.setItem(ACTIVE_REVIEW_JOB_KEY, JSON.stringify({
        pollUrl,
        jobId: job.job_id || options.jobId || "",
        startedAt: started,
        filename: options.filename || ""
      }));

      if (job.status === "completed") {
        const review = await fetchCompletedReview(job);
        localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
        return review;
      }
      if (job.status === "failed") {
        localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
        const terminalError = new Error(
          job.error || job.message || "The review could not be completed."
        );
        terminalError.terminal = true;
        throw terminalError;
      }

      if (Date.now() - started > 30 * 60 * 1000) {
        loadingMessage.textContent =
          "The review is still processing. You may leave this page and return later. The portal will reconnect to the active review automatically.";
      }
    } catch (error) {
      if (error && error.terminal) {
        throw error;
      }

      temporaryFailures += 1;
      pollDelay = Math.min(15000, 2500 + temporaryFailures * 1500);

      if (temporaryFailures >= 12) {
        loadingMessage.textContent =
          "The portal cannot currently reach the review service. It will keep trying automatically.";
      } else {
        loadingMessage.textContent =
          "The connection was interrupted. Reconnecting to the review job…";
      }
    }
  }

  throw new Error(
    "The review has not completed within two hours. The job has been saved in your review history. Check the portal later or contact the administrator."
  );
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const oldError = document.querySelector(".error-banner");
  if (oldError) oldError.remove();

  const scope = selectedScope();
  const stage = selectedStage();
  const chapter = Number(chapterSelect.value || 0);
  const rangeEnd = Number(combinedChapterEnd.value || 0);
  if (scope === "chapter" && !chapter) {
    chapterSelect.focus();
    return;
  }
  if (scope === "chapter_range" && !rangeEnd) {
    combinedChapterEnd.focus();
    return;
  }
  if (stage === "revised" && !(supervisorCommentFilesInput.files || []).length && !supervisorCommentsText.value.trim()) {
    showFormError("Upload the supervisor comments or paste them into the comments box before reviewing a revised chapter.", revisionReviewFields); return;
  }

  emptyState.classList.add("hidden"); resultsState.classList.add("hidden"); loadingState.classList.remove("hidden");
  progressBar.style.width = "2%"; progressText.textContent = "2%"; loadingMessage.textContent = "Uploading and queuing the review";
  submitButton.disabled = true; submitButton.querySelector("span").textContent = "Review in progress…";

  try {
    const body = new FormData(form);
    if (scope === "full_thesis") {
      body.set("selected_chapter", "0");
      body.set("combined_chapter_end", "0");
      body.set("document_type", "full_thesis");
      body.delete("previous_files");
    } else if (scope === "chapter_range") {
      body.set("selected_chapter", String(rangeEnd));
      body.set("combined_chapter_end", String(rangeEnd));
      body.set("document_type", "combined_chapters");
      body.delete("previous_files");
    } else {
      body.set("combined_chapter_end", "0");
    }
    if (stage !== "revised") { body.delete("supervisor_comment_files"); body.delete("supervisor_comments_text"); body.delete("original_file"); }
    const response = await fetch("/api/review", { method: "POST", body, headers: { "Accept": "application/json" } });
    const queued = await readJsonSafely(response);
    updateProgress(queued);
    const activeJob = {
      pollUrl: queued.poll_url,
      jobId: queued.job_id,
      startedAt: Date.now(),
      filename: fileInput.files[0]?.name || ""
    };
    localStorage.setItem(ACTIVE_REVIEW_JOB_KEY, JSON.stringify(activeJob));
    const review = await waitForReview(queued.poll_url, activeJob);
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


async function resumeActiveReviewJob() {
  const raw = localStorage.getItem(ACTIVE_REVIEW_JOB_KEY);
  if (!raw) return;

  let activeJob = null;
  try {
    activeJob = JSON.parse(raw);
  } catch (_) {
    localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
    return;
  }

  if (!activeJob?.pollUrl) {
    localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
    return;
  }

  emptyState.classList.add("hidden");
  resultsState.classList.add("hidden");
  loadingState.classList.remove("hidden");
  progressBar.style.width = "4%";
  progressText.textContent = "4%";
  loadingMessage.textContent = activeJob.filename
    ? `Reconnecting to the review of ${activeJob.filename}…`
    : "Reconnecting to the active review…";

  try {
    const review = await waitForReview(activeJob.pollUrl, activeJob);
    renderReview(review);
    loadingState.classList.add("hidden");
    resultsState.classList.remove("hidden");
  } catch (error) {
    loadingState.classList.add("hidden");
    emptyState.classList.remove("hidden");
    localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
    showFormError(error.message);
  }
}

updateUploadWorkflow();

resumeActiveReviewJob();
