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
const phdChapterOptions = [...chapterSelect.querySelectorAll(".phd-chapter-option")];
const phdRangeOptions = [...combinedChapterEnd.querySelectorAll(".phd-range-option")];
const doctoralNote = document.getElementById("doctoralNote");
const reviewDepthHelp = document.getElementById("reviewDepthHelp");
const lightReviewNote = document.getElementById("lightReviewNote");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const loadingMessage = document.getElementById("loadingMessage");
const stopReviewButton = document.getElementById("stopReviewButton");
const scopeStructureHelp = document.getElementById("scopeStructureHelp");
const workflowHelp = document.getElementById("workflowHelp");
const assessmentMetadataFields = document.getElementById("assessmentMetadataFields");
const degreeProgramme = document.getElementById("degreeProgramme");
const thesisTitle = document.getElementById("thesisTitle");
const assessmentStage = document.getElementById("assessmentStage");
const reviewScopeField = document.getElementById("reviewScopeField");
const submissionStageField = document.getElementById("submissionStageField");
const reviewDepthField = document.getElementById("reviewDepthField");
const submitButtonLabel = document.getElementById("submitButtonLabel");
const externalAssessmentSection = document.getElementById("externalAssessmentSection");
const externalReportButton = document.getElementById("externalReportButton");
const correctionsScheduleButton = document.getElementById("correctionsScheduleButton");
const confidentialRecommendationButton = document.getElementById("confidentialRecommendationButton");
const oralQuestionsButton = document.getElementById("oralQuestionsButton");
const priorExaminerFields = document.getElementById("priorExaminerFields");
const priorExaminerFilesInput = document.getElementById("priorExaminerFilesInput");
const priorExaminerFileNames = document.getElementById("priorExaminerFileNames");
const priorExaminerCommentsText = document.getElementById("priorExaminerCommentsText");
const priorVersionFileInput = document.getElementById("priorVersionFileInput");
const priorVersionFileName = document.getElementById("priorVersionFileName");
const workflowFormNote = document.getElementById("workflowFormNote");

let highestDisplayedProgress = 2;

function setProgress(value, message = "", { reset = false } = {}) {
  const incoming = Math.max(
    2,
    Math.min(100, Number(value || 2))
  );

  if (reset) {
    highestDisplayedProgress = incoming;
  } else {
    highestDisplayedProgress = Math.max(
      highestDisplayedProgress,
      incoming
    );
  }

  progressBar.style.width = `${highestDisplayedProgress}%`;
  progressBar.dataset.progress = String(highestDisplayedProgress);
  progressText.textContent = `${highestDisplayedProgress}%`;

  if (message) {
    loadingMessage.textContent = message;
  }

  return highestDisplayedProgress;
}

function updateDepthGuidance() {
  const doctoral = ["Professional Doctorate", "PhD"].includes(academicLevelSelect.value);
  const external = selectedWorkflow() === "external_assessment";
  doctoralNote.classList.toggle("hidden", !doctoral || external);
  if (external) {
    const targetDepth = doctoral
      ? "advanced"
      : academicLevelSelect.value === "Research Masters / MPhil"
        ? "standard"
        : "light";
    const depthInput = form.querySelector(`input[name="review_depth"][value="${targetDepth}"]`);
    if (depthInput) depthInput.checked = true;
    reviewDepthHelp.textContent = "External Assessment automatically applies the examination standard appropriate to the academic level shown above.";
    lightReviewNote.classList.add("hidden");
    return;
  }
  const depth = form.querySelector('input[name="review_depth"]:checked')?.value || "standard";
  const levelLabel = academicLevelSelect.options[academicLevelSelect.selectedIndex]?.text || "the academic level shown above";
  const level = academicLevelSelect.value;
  lightReviewNote.classList.toggle("hidden", depth !== "light");
  const levelFocus = {
    "Bachelors": "problem clarity, basic literature integration, correct methods, accurate analysis and a modest explicit contribution",
    "Non-Research Masters": "an advanced applied problem, integrated literature, justified professional methods, credible interpretation and feasible recommendations",
    "Research Masters / MPhil": "critical synthesis, theory, construct roles, problem-gap evidence, alignment, methodological defensibility, citation integrity and a research contribution",
    "Professional Doctorate": "doctoral scholarship, a consequential practice or policy problem, methodological robustness, reflexivity, implementation and an original contribution to professional practice",
    "PhD": "authoritative scholarship, theoretical and methodological rigour, robustness, rival explanations and an original contribution to knowledge",
  }[level] || "the requirements of the declared programme";
  if (depth === "light") {
    reviewDepthHelp.textContent = `Light Review remains at the ${levelLabel} standard and checks ${levelFocus}, but reports only the most material issues.`;
  } else if (depth === "advanced") {
    reviewDepthHelp.textContent = `Advanced Review applies the full ${levelLabel} benchmark, including ${levelFocus}, with expanded coverage and an independent expert audit.`;
  } else {
    reviewDepthHelp.textContent = `Standard Review applies the full ${levelLabel} benchmark, including ${levelFocus}, with a degree-calibrated independent accuracy audit.`;
  }

}
academicLevelSelect.addEventListener("change", () => {
  updateDepthGuidance();
  updateUploadWorkflow();
});
form.querySelectorAll('input[name="review_depth"]').forEach(input => input.addEventListener("change", updateDepthGuidance));
form.querySelectorAll('input[name="workflow_type"]').forEach(input => input.addEventListener("change", () => { updateDepthGuidance(); updateUploadWorkflow(); }));
updateDepthGuidance();

function selectedWorkflow() {
  return document.querySelector('input[name="workflow_type"]:checked')?.value || "supervisory_review";
}

function selectedScope() {
  return document.querySelector('input[name="review_scope"]:checked')?.value || "chapter";
}

function selectedDocumentType() {
  return document.querySelector('input[name="document_type"]:checked')?.value || "chapter_one";
}

function selectedStage() {
  return document.querySelector('input[name="submission_stage"]:checked')?.value || "initial";
}

function updatePhdChapterOptions() {
  const isPhd = academicLevelSelect.value === "PhD";
  [...phdChapterOptions, ...phdRangeOptions].forEach(option => {
    option.hidden = !isPhd;
    option.disabled = !isPhd;
  });
  if (!isPhd && Number(chapterSelect.value || 0) > 5) chapterSelect.value = "";
  if (!isPhd && Number(combinedChapterEnd.value || 0) > 5) combinedChapterEnd.value = "";
}

function updateUploadWorkflow() {
  updatePhdChapterOptions();
  const external = selectedWorkflow() === "external_assessment";
  if (external) {
    const fullScope = form.querySelector('input[name="review_scope"][value="full_thesis"]');
    if (fullScope) fullScope.checked = true;
  }
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
  const phd = academicLevelSelect.value === "PhD";

  assessmentMetadataFields.classList.toggle("hidden", !external);
  assessmentStage.disabled = !external;
  const correctionVerification = external && assessmentStage.value !== "initial_examination";
  priorExaminerFields.classList.toggle("hidden", !correctionVerification);
  priorExaminerFilesInput.disabled = !correctionVerification;
  priorExaminerCommentsText.disabled = !correctionVerification;
  priorVersionFileInput.disabled = !correctionVerification;
  degreeProgramme.disabled = !external;
  thesisTitle.disabled = !external;
  degreeProgramme.required = external;
  thesisTitle.required = external;
  reviewScopeField.classList.toggle("hidden", external);
  submissionStageField.classList.toggle("hidden", external);
  reviewDepthField.classList.toggle("hidden", external);
  if (workflowHelp) {
    workflowHelp.textContent = external
      ? "Produces an independent external examiner judgement, correction schedule, confidential recommendation and oral examination questions."
      : "Provides detailed developmental guidance, annotated comments and a supervisor review report.";
  }
  submitButtonLabel.textContent = external
    ? "Submit thesis for external assessment"
    : "Submit your work for expert review";
  workflowFormNote.textContent = external
    ? "The external assessment is an examiner-ready draft. The authorised external examiner must review, confirm and sign the final institutional report."
    : "For revised chapters, the assistant checks every extracted supervisor comment and reports whether it is addressed, partly addressed, not addressed, or requires manual confirmation.";

  if (scopeStructureHelp) {
    if (combined) {
      scopeStructureHelp.textContent =
        "Professional combined-chapter review assesses every chapter in the selected range separately, then checks sequential alignment across the chapters.";
    } else if (fullThesis) {
      scopeStructureHelp.textContent = phd
        ? "PhD examiner mode accepts custom chapter numbers, order and titles, then verifies that all prescribed doctoral elements are present, integrated and supported across the complete thesis."
        : "Examiner mode applies the standard five-chapter structure, checks all required research functions, audits methods and results, and gives a whole-thesis recommendation.";
    } else {
      scopeStructureHelp.textContent =
        "Professional chapter review assesses every section and subsection of the selected chapter and uses other supplied chapters only for relevant alignment checks.";
    }
  }

  chapterField.classList.toggle("hidden", external || fullThesis || combined);
  chapterSelect.required = !external && !fullThesis && !combined;
  chapterSelect.disabled = external || fullThesis || combined;

  combinedChapterField.classList.toggle("hidden", external || !combined);
  combinedChapterEnd.required = combined;
  if (external) combinedChapterEnd.required = false;
  combinedChapterEnd.disabled = external || !combined;

  documentTypeField.classList.toggle(
    "hidden",
    external || fullThesis || combined || chapter !== 1
  );
  previousChaptersField.classList.toggle(
    "hidden",
    external || fullThesis || combined || chapter < 2
  );
  previousFilesInput.required = false;
  previousFilesInput.disabled = external || fullThesis || combined || chapter < 2;

  revisionReviewFields.classList.toggle("hidden", external || !revised);
  supervisorCommentFilesInput.disabled = external || !revised;
  supervisorCommentsText.disabled = external || !revised;
  originalFileInput.disabled = external || !revised;

  const prefix = revised ? "Choose the revised " : "Choose ";
  if (external) {
    mainUploadTitle.textContent = "Choose the complete thesis or dissertation for external examination";
    return;
  }
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

priorExaminerFilesInput.addEventListener("change", () => {
  setFileNames(priorExaminerFilesInput, priorExaminerFileNames, "No earlier examiner file selected");
});

priorVersionFileInput.addEventListener("change", () => {
  priorVersionFileName.textContent = priorVersionFileInput.files[0]?.name || "No earlier thesis selected";
});

assessmentStage.addEventListener("change", updateUploadWorkflow);

document.querySelectorAll('input[name="review_scope"], input[name="document_type"], input[name="submission_stage"], input[name="workflow_type"]').forEach(input => {
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
    ? (currentReview?.external_assessment ? "Earlier Examiner Correction" : "Supervisor Follow-up")
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
  const external = Boolean(review.external_assessment);
  const original = review.original_document;
  const sourceRows = sources.map(source =>
    `<div class="context-file"><strong>${escapeHtml(source)}</strong><span>${external ? "Earlier examiner report" : "Supervisor comments"}</span></div>`
  );
  if (original) {
    sourceRows.push(`<div class="context-file"><strong>${escapeHtml(original.filename)}</strong><span>Original version used for comparison</span></div>`);
  }
  return sourceRows.join("");
}

const EXTERNAL_DOMAIN_LABELS = {
  chapter_one_assessment: "Chapter One or Foundational Chapter",
  research_problem_and_purpose: "Research Problem and Purpose",
  literature_and_theoretical_foundation: "Literature and Theoretical Foundation",
  methodology_and_procedures: "Methodology and Procedures",
  results_or_findings: "Results or Findings",
  discussion_and_interpretation: "Discussion and Interpretation",
  conclusions_recommendations_and_contribution: "Conclusions, Recommendations and Contribution",
  structural_coherence_and_alignment: "Structural Coherence and Alignment",
  academic_writing_and_presentation: "Academic Writing and Presentation",
  ethics_and_research_integrity: "Ethics and Research Integrity",
  originality_and_contribution: "Originality and Contribution",
};

function externalJudgementLabel(value) {
  return String(value || "Not assessed")
    .replaceAll("_", " ")
    .replace(/\b\w/g, character => character.toUpperCase());
}

function renderExternalAssessment(review) {
  const assessment = review.external_assessment;
  const isExternal = Boolean(assessment);
  externalAssessmentSection.classList.toggle("hidden", !isExternal);
  [externalReportButton, correctionsScheduleButton, confidentialRecommendationButton, oralQuestionsButton]
    .forEach(button => button.classList.toggle("hidden", !isExternal));
  if (!isExternal) return;

  document.getElementById("externalRecommendation").textContent = assessment.recommendation_label || "External recommendation pending";
  document.getElementById("externalRationale").textContent = assessment.recommendation_rationale || "";
  document.getElementById("chapterOneGateBadge").textContent = `Chapter One: ${externalJudgementLabel(assessment.chapter_one_gate_status)}`;

  const domains = (assessment.domain_order || Object.keys(EXTERNAL_DOMAIN_LABELS))
    .map(key => [key, assessment[key]])
    .filter(([, value]) => value && typeof value === "object");
  document.getElementById("externalDomainList").innerHTML = domains.map(([key, domain]) => `
    <article class="assessment-domain">
      <div><strong>${escapeHtml(EXTERNAL_DOMAIN_LABELS[key] || key)}</strong><span class="domain-judgement judgement-${escapeHtml(domain.judgement)}">${escapeHtml(externalJudgementLabel(domain.judgement))}</span></div>
      <p>${escapeHtml(domain.assessment)}</p>
      ${(domain.concerns || []).length ? `<details><summary>Material concerns</summary><ul>${domain.concerns.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>` : ""}
    </article>`).join("");

  const corrections = assessment.corrections || [];
  document.getElementById("externalCorrectionsList").innerHTML = corrections.length
    ? corrections.map(item => `
      <article class="correction-item ${escapeHtml(item.classification)}">
        <div><strong>${escapeHtml(String(item.number))}. ${escapeHtml(item.chapter_or_section)}</strong><span>${escapeHtml(item.classification)}</span></div>
        <small>${escapeHtml(item.location || "Location to be confirmed")}</small>
        <p><b>Issue:</b> ${escapeHtml(item.issue)}</p>
        <p><b>Required correction:</b> ${escapeHtml(item.required_correction)}</p>
      </article>`).join("")
    : `<p class="form-note">No formal corrections were recorded.</p>`;

  const id = encodeURIComponent(review.review_id);
  externalReportButton.onclick = () => { window.location.href = `/api/review/${id}/external-report.docx`; };
  correctionsScheduleButton.onclick = () => { window.location.href = `/api/review/${id}/corrections-schedule.docx`; };
  confidentialRecommendationButton.onclick = () => { window.location.href = `/api/review/${id}/confidential-recommendation.docx`; };
  oralQuestionsButton.onclick = () => { window.location.href = `/api/review/${id}/oral-questions.docx`; };
}

function renderReview(review) {
  currentReview = review;
  const s = review.summary;
  const isExternal = Boolean(review.external_assessment);
  document.getElementById("resultTitle").textContent = isExternal
    ? `External assessment: ${s.filename}`
    : `${s.document_label}: ${s.filename}`;
  document.getElementById("overallScore").textContent = isExternal ? "EXAM" : `${s.overall_score}%`;
  document.getElementById("readinessLabel").textContent = s.readiness_label;
  document.getElementById("readinessMeaning").textContent = s.readiness_meaning;

  const correctionCounts = review.external_assessment?.correction_counts || {};
  const metricRows = isExternal ? [
    metric("Chapter One gate", externalJudgementLabel(s.chapter_one_gate_status)),
    metric("Critical corrections", correctionCounts.critical || 0),
    metric("Major corrections", correctionCounts.major || 0),
    metric("Moderate corrections", correctionCounts.moderate || 0),
    metric("Minor corrections", correctionCounts.minor || 0),
    metric("Academic evidence review", `${s.academic_review_score}%`),
  ] : [
    metric("Academic review", `${s.academic_review_score}%`),
    metric("Alignment", s.alignment_score == null ? "N/A" : `${s.alignment_score}%`),
    metric("Critical issues", s.critical_issues || 0),
    metric("Major issues", s.major_issues || 0),
    metric("Moderate issues", s.moderate_issues || 0),
    metric("Strengths", s.strengths_identified || 0),
    metric("DOCX comment boxes", s.native_docx_comment_count == null ? "Pending" : `${s.native_docx_comment_count}/${s.expected_native_docx_comment_count || s.native_docx_comment_count}`),
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
  document.getElementById("revisionEyebrow").textContent = isExternal
    ? "Earlier examiner correction follow-up"
    : "Revised chapter follow-up";
  document.getElementById("revisionHeading").textContent = isExternal
    ? "Correction verification"
    : "Supervisor comment compliance";
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

  renderExternalAssessment(review);
  const annotatedButton = document.getElementById("annotatedButton");
  const inlineAnnotatedButton = document.getElementById("inlineAnnotatedButton");
  if (s.annotated_document_available) {
    annotatedButton.classList.remove("hidden");
    annotatedButton.disabled = false;
    annotatedButton.onclick = () => {
      window.location.href = `/api/review/${encodeURIComponent(review.review_id)}/annotated.docx`;
    };
    if (inlineAnnotatedButton) {
      inlineAnnotatedButton.classList.remove("hidden");
      inlineAnnotatedButton.disabled = false;
      inlineAnnotatedButton.onclick = () => {
        window.location.href = `/api/review/${encodeURIComponent(review.review_id)}/annotated-inline.docx`;
      };
    }
  } else {
    annotatedButton.classList.add("hidden");
    if (inlineAnnotatedButton) inlineAnnotatedButton.classList.add("hidden");
  }

  const downloadButton = document.getElementById("downloadButton");
  downloadButton.classList.toggle("hidden", isExternal);
  downloadButton.onclick = () => {
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
  return setProgress(
    job.progress || 2,
    job.message || "Reviewing the document"
  );
}

async function fetchCompletedReview(job) {
  if (job.review && typeof job.review === "object") return job.review;
  const resultUrl = job.result_url || (job.review_id ? `/api/review/${encodeURIComponent(job.review_id)}` : "");
  if (!resultUrl) throw new Error("The review finished, but the result location was not returned.");
  const response = await fetch(resultUrl, { headers: { "Accept": "application/json" } });
  return await readJsonSafely(response);
}

async function requestJobResume(resumeUrl) {
  if (!resumeUrl) return false;
  const csrf = form.querySelector('input[name="csrf_token"]')?.value || "";
  const body = new FormData();
  body.set("csrf_token", csrf);
  const response = await fetch(resumeUrl, {
    method: "POST",
    body,
    headers: { "Accept": "application/json" },
  });
  if (!response.ok) return false;
  return true;
}

function setStopReviewUrl(stopUrl) {
  if (!stopReviewButton) return;
  if (stopUrl) {
    stopReviewButton.dataset.stopUrl = stopUrl;
    stopReviewButton.classList.remove("hidden");
    stopReviewButton.disabled = false;
    stopReviewButton.textContent = "Stop review";
  } else {
    stopReviewButton.dataset.stopUrl = "";
    stopReviewButton.classList.add("hidden");
  }
}

async function requestJobStop(stopUrl) {
  if (!stopUrl) return false;
  const csrf = form.querySelector('input[name="csrf_token"]')?.value || "";
  const body = new FormData();
  body.set("csrf_token", csrf);
  const response = await fetch(stopUrl, {
    method: "POST",
    body,
    headers: { "Accept": "application/json" },
  });
  await readJsonSafely(response);
  return true;
}

if (stopReviewButton) {
  stopReviewButton.addEventListener("click", async () => {
    const stopUrl = stopReviewButton.dataset.stopUrl || "";
    if (!stopUrl) return;
    const confirmed = window.confirm(
      "Stop this review? Completed checkpoints will be kept and you can resume later."
    );
    if (!confirmed) return;
    stopReviewButton.disabled = true;
    stopReviewButton.textContent = "Stopping…";
    loadingMessage.textContent = "Stopping the review safely and saving completed checkpoints…";
    try {
      await requestJobStop(stopUrl);
      localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
      window.location.assign("/portal");
    } catch (error) {
      stopReviewButton.disabled = false;
      stopReviewButton.textContent = "Stop review";
      showFormError(error.message || "The review could not be stopped.");
    }
  });
}

async function waitForReview(pollUrl, options = {}) {
  const started = Number(options.startedAt || Date.now());
  const maximumWait = 2 * 60 * 60 * 1000;
  let temporaryFailures = 0;
  let pollDelay = 2500;
  let resumeRequested = false;
  let recoveryFirstSeenAt = 0;
  let autoResumeFailures = 0;

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
      const highestProgress = updateProgress(job);
      setStopReviewUrl(job.stop_url || (job.job_id ? `/api/review/jobs/${encodeURIComponent(job.job_id)}/stop` : ""));

      localStorage.setItem(ACTIVE_REVIEW_JOB_KEY, JSON.stringify({
        pollUrl,
        jobId: job.job_id || options.jobId || "",
        startedAt: started,
        filename: options.filename || "",
        highestProgress
      }));

      if (job.status === "stopped") {
        localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
        setStopReviewUrl("");
        const stoppedError = new Error(
          job.message || "The review was stopped. Completed checkpoints were retained."
        );
        stoppedError.terminal = true;
        stoppedError.stopped = true;
        throw stoppedError;
      }
      if (job.status === "completed") {
        setStopReviewUrl("");
        const review = await fetchCompletedReview(job);
        localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
        return review;
      }
      if (job.status === "queued" && job.recoverable) {
        const savedUnits = Number(job.completed_units || job.checkpoint_count || 0);
        loadingMessage.textContent = savedUnits
          ? `${job.message || "Retrying the interrupted stage automatically"} · ${savedUnits} checkpoint${savedUnits === 1 ? "" : "s"} saved`
          : (job.message || "Retrying the interrupted stage automatically");
        pollDelay = 4000;
        continue;
      }
      if (job.status === "failed" && job.resume_url) {
        const savedUnits = Number(job.completed_units || job.checkpoint_count || 0);
        if (!recoveryFirstSeenAt) recoveryFirstSeenAt = Date.now();
        const maxRecoveryMs = Math.max(60, Number(job.client_auto_recovery_seconds || 600)) * 1000;
        if (job.auto_resume_allowed === false || Date.now() - recoveryFirstSeenAt > maxRecoveryMs || autoResumeFailures >= 1) {
          localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
          setStopReviewUrl("");
          const message = job.error || job.message || (
            savedUnits
              ? `Automatic recovery stopped after ${savedUnits} saved checkpoint${savedUnits === 1 ? "" : "s"}. Open Review History and select Recover once, or submit the document again.`
              : "Automatic recovery stopped. Open Review History and select Recover once, or submit the document again."
          );
          const terminalError = new Error(message);
          terminalError.terminal = true;
          throw terminalError;
        }

        loadingMessage.textContent = savedUnits
          ? `The review stopped safely with ${savedUnits} completed checkpoint${savedUnits === 1 ? "" : "s"}. Recovering the interrupted stage…`
          : "The review stopped safely. Recovering the interrupted stage…";
        if (!resumeRequested) {
          resumeRequested = true;
          const ok = await requestJobResume(job.resume_url);
          if (!ok) autoResumeFailures += 1;
        }
        pollDelay = 5000;
        continue;
      }
      if (job.status === "failed") {
        localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
        setStopReviewUrl("");
        const terminalError = new Error(
          job.error || job.message || "The review could not be completed."
        );
        terminalError.terminal = true;
        throw terminalError;
      }
      if (job.status === "paused" && job.recoverable) {
        const savedUnits = Number(job.completed_units || job.checkpoint_count || 0);
        if (!recoveryFirstSeenAt) recoveryFirstSeenAt = Date.now();
        const maxRecoveryMs = Math.max(60, Number(job.client_auto_recovery_seconds || 600)) * 1000;
        if (job.auto_resume_allowed === false || Date.now() - recoveryFirstSeenAt > maxRecoveryMs) {
          localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
          setStopReviewUrl("");
          const terminalError = new Error(
            savedUnits
              ? `Automatic recovery stopped after ${savedUnits} saved checkpoint${savedUnits === 1 ? "" : "s"}. Open Review History and select Resume once, or submit the document again.`
              : "Automatic recovery stopped. Open Review History and select Resume once, or submit the document again."
          );
          terminalError.terminal = true;
          throw terminalError;
        }
        loadingMessage.textContent = savedUnits
          ? `Review paused safely with ${savedUnits} completed checkpoint${savedUnits === 1 ? "" : "s"}. Resuming from the last saved point…`
          : "Review paused safely. Resuming from the last saved point…";
        if (
          !resumeRequested
          && job.resume_url
          && job.auto_resume_allowed !== false
        ) {
          resumeRequested = true;
          try {
            await requestJobResume(job.resume_url);
          } catch (_) {
            // The server-side automatic recovery may still resume the job.
          }
        }
        pollDelay = 5000;
        continue;
      }

      if (job.current_stage && job.checkpoint_count) {
        loadingMessage.textContent = `${job.message || "Reviewing the document"} · ${job.checkpoint_count} checkpoint${job.checkpoint_count === 1 ? "" : "s"} saved`;
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

  const external = selectedWorkflow() === "external_assessment";
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
  if (external && !degreeProgramme.value.trim()) {
    showFormError("Enter the degree programme for the external examination report.", assessmentMetadataFields);
    degreeProgramme.focus();
    return;
  }
  if (external && !thesisTitle.value.trim()) {
    showFormError("Enter the thesis or dissertation title for the external examination report.", assessmentMetadataFields);
    thesisTitle.focus();
    return;
  }
  if (external && assessmentStage.value !== "initial_examination" && !(priorExaminerFilesInput.files || []).length && !priorExaminerCommentsText.value.trim()) {
    showFormError("Upload the earlier examiner report or paste the correction schedule before re-examination or corrected-thesis verification.", priorExaminerFields);
    return;
  }
  if (!external && stage === "revised" && !(supervisorCommentFilesInput.files || []).length && !supervisorCommentsText.value.trim()) {
    showFormError("Upload the supervisor comments or paste them into the comments box before reviewing a revised chapter.", revisionReviewFields); return;
  }

  emptyState.classList.add("hidden"); resultsState.classList.add("hidden"); loadingState.classList.remove("hidden");
  setProgress(
    2,
    external
      ? "Uploading and queuing the external assessment"
      : "Uploading and queuing the review",
    { reset: true }
  );
  submitButton.disabled = true; submitButton.querySelector("span").textContent = external ? "External assessment in progress…" : "Review in progress…";

  try {
    const body = new FormData(form);
    if (external) {
      body.set("review_scope", "full_thesis");
      body.set("selected_chapter", "0");
      body.set("combined_chapter_end", "0");
      body.set("document_type", "full_thesis");
      body.set("submission_stage", "initial");
      body.delete("previous_files");
      body.delete("supervisor_comment_files");
      body.delete("supervisor_comments_text");
      body.delete("original_file");
    } else if (scope === "full_thesis") {
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
    if (external || stage !== "revised") { body.delete("supervisor_comment_files"); body.delete("supervisor_comments_text"); body.delete("original_file"); }
    const response = await fetch("/api/review", { method: "POST", body, headers: { "Accept": "application/json" } });
    const queued = await readJsonSafely(response);
    updateProgress(queued);
    const activeJob = {
      pollUrl: queued.poll_url,
      jobId: queued.job_id,
      startedAt: Date.now(),
      filename: fileInput.files[0]?.name || "",
      highestProgress: highestDisplayedProgress
    };
    localStorage.setItem(ACTIVE_REVIEW_JOB_KEY, JSON.stringify(activeJob));
    setStopReviewUrl(queued.stop_url || `/api/review/jobs/${encodeURIComponent(queued.job_id)}/stop`);
    const review = await waitForReview(queued.poll_url, activeJob);
    renderReview(review);
    loadingState.classList.add("hidden"); resultsState.classList.remove("hidden");
  } catch (error) {
    setStopReviewUrl("");
    if (error && error.stopped) {
      window.location.assign("/portal");
      return;
    }
    loadingState.classList.add("hidden"); emptyState.classList.remove("hidden"); showFormError(error.message);
  } finally {
    submitButton.disabled = false; submitButton.querySelector("span").textContent = selectedWorkflow() === "external_assessment" ? "Submit thesis for external assessment" : "Run expert review";
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
  setProgress(
    Math.max(4, Number(activeJob.highestProgress || 4)),
    activeJob.filename
      ? `Reconnecting to the review of ${activeJob.filename}…`
      : "Reconnecting to the active review…",
    { reset: true }
  );

  setStopReviewUrl(activeJob.jobId ? `/api/review/jobs/${encodeURIComponent(activeJob.jobId)}/stop` : "");

  try {
    const review = await waitForReview(activeJob.pollUrl, activeJob);
    renderReview(review);
    loadingState.classList.add("hidden");
    resultsState.classList.remove("hidden");
  } catch (error) {
    setStopReviewUrl("");
    loadingState.classList.add("hidden");
    emptyState.classList.remove("hidden");
    localStorage.removeItem(ACTIVE_REVIEW_JOB_KEY);
    if (error && error.stopped) {
      window.location.assign("/portal");
      return;
    }
    showFormError(error.message);
  }
}

updateUploadWorkflow();

resumeActiveReviewJob();
