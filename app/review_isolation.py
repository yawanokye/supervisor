from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Tuple

# V-Professor applies generic academic standards across jobs. Study-specific
# names, constructs, wording, examples and detected weaknesses belong only to
# the current job and must never become defaults for another submission.
ISOLATION_POLICY_VERSION = "current-submission-only-v1"

_STALE_KEYS = {
    "training_examples",
    "example_review",
    "example_findings",
    "benchmark_findings",
    "learned_rules",
    "learned_findings",
    "prior_submission_context",
    "previous_submission_context",
    "historical_review_context",
    "cross_job_context",
}


def _remove_stale_keys(mapping: MutableMapping[str, Any]) -> None:
    for key in list(mapping):
        normal = str(key or "").strip().lower()
        if normal in _STALE_KEYS or normal.startswith(("sample_", "learned_", "cross_job_")):
            mapping.pop(key, None)


def enforce_current_submission_isolation(
    review: Mapping[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
    *,
    document_hash: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return job-local review data with cross-submission context disabled.

    Previous chapters supplied as context for the *same* submission remain
    available. Only explicit sample, training, benchmark or prior-submission
    fields are removed. The function does not retain document content globally.
    """
    isolated_review = deepcopy(dict(review or {}))
    isolated_runtime = deepcopy(dict(runtime_context or {}))
    _remove_stale_keys(isolated_review)
    _remove_stale_keys(isolated_runtime)

    summary = isolated_review.setdefault("summary", {})
    summary["study_specific_context_policy"] = ISOLATION_POLICY_VERSION
    summary["cross_submission_learning"] = False
    summary["example_content_persisted"] = False
    if document_hash:
        summary["current_submission_fingerprint"] = str(document_hash)[:16]

    isolated_runtime["study_specific_context_policy"] = ISOLATION_POLICY_VERSION
    isolated_runtime["cross_submission_learning"] = False
    isolated_runtime["current_submission_only"] = True
    return isolated_review, isolated_runtime


def context_lock_isolation_fields() -> Dict[str, Any]:
    return {
        "study_specific_context_policy": ISOLATION_POLICY_VERSION,
        "current_submission_only": True,
        "cross_submission_learning": False,
        "persist_example_terms_as_rules": False,
    }
