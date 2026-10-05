"""One bounded prose repair for released comments; never edits findings or evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re

from .ai_schemas import StrictModel
from .model_router import CostAwareAIProvider, ReviewStage
from .natural_supervisor_comment import natural_supervisor_comment
from .provider_state import provider_checkpoint_context
from .supplementary_usage import append_usage
from .supervisory_voice import VOICE_CONTRACT, comment_variation_audit, usable_narrative, narrative_basis


class CommentRevision(StrictModel):
    finding_id: str
    supervisory_comment: str


class CommentRevisions(StrictModel):
    comments: list[CommentRevision]


async def polish_selected_comments(review: dict, checkpoints, config) -> dict:
    rows = review.get("canonical_findings") or []
    actionable = [r for r in rows if r.get("status") in {
        "partly_meets_requirement", "does_not_meet_requirement", "manual_review_required"}]
    audit = comment_variation_audit(actionable)
    review["comment_quality_audit"] = audit
    if not config.enabled or not (config.openai_configured or config.deepseek_configured):
        audit["prose_repair_status"] = "not run: AI disabled or unconfigured"
        return review
    if os.getenv("AI_COMMENT_PROSE_REPAIR_ENABLED", "true").lower() in {"0", "false", "no"}:
        audit["prose_repair_status"] = "disabled"
        return review
    duplicate_numbers = {n for pair in audit["near_duplicate_comment_pairs"] for n in pair}
    repeated = audit["repeated_openings"]
    suspect = []
    for n, row in enumerate(actionable, 1):
        opening = " ".join(re.findall(r"\w+", natural_supervisor_comment(row).lower())[:4])
        if not usable_narrative(row) or opening in repeated or n in duplicate_numbers:
            suspect.append(row)
    # Work only on the released shortlist, in bounded batches with a fixed output ceiling.
    suspect = suspect[:max(1, int(os.getenv("AI_COMMENT_PROSE_REPAIR_MAX_COMMENTS", "65")))]
    if not suspect:
        audit["prose_repair_status"] = "not needed"
        return review
    evidence = [{"finding_id":str(r.get("finding_id") or r.get("number") or i),
        **{k:r.get(k) for k in ("item", "category", "severity", "assessment", "comment",
            "problematic_quote", "exact_source_text", "academic_consequence", "required_action")}}
        for i,r in enumerate(suspect)]
    provider = CostAwareAIProvider(config)
    route = provider.route_signature(stage=ReviewStage.COMMENT_DEDUPLICATION,review_depth="standard",
        requested_model=config.openai_chapter_model,requested_effort=config.openai_chapter_reasoning_effort)
    revised = {}; extra_usage = []
    batch_size = max(1,min(24,int(os.getenv("AI_COMMENT_PROSE_REPAIR_BATCH_SIZE","24"))))
    for offset in range(0,len(evidence),batch_size):
        prompt = json.dumps({"findings":evidence[offset:offset+batch_size],"existing_comment_openings":list(repeated),
            "instruction":"Rewrite each finding as one natural margin comment. Preserve ALL required corrective actions and the diagnosis. Add no new factual claims, citations, figures, assumptions or faults. Do not change certainty. Vary the shape according to the problem; do not force questions or praise. Return every finding_id exactly once.",
            "voice":VOICE_CONTRACT},ensure_ascii=False)
        digest = hashlib.sha256((prompt+route).encode()).hexdigest()
        key = "comment-prose-"+digest[:22]
        result = checkpoints.load_provider_result(key,expected_input_hash=digest)
        if result is None:
            with provider_checkpoint_context(checkpoints,key):
                result = await provider.complete_json(model=config.openai_chapter_model,
                    system_prompt="You are editing verified supervisory comments. "+VOICE_CONTRACT,
                    user_prompt=prompt,schema_model=CommentRevisions,purpose="selected_comment_prose_repair",
                    reasoning_effort=config.openai_chapter_reasoning_effort,max_output_tokens=7000,
                    stage=ReviewStage.COMMENT_DEDUPLICATION,review_depth="standard",allow_escalation=False)
            checkpoints.save_provider_result(key,result,input_hash=digest)
        append_usage(review.setdefault("ai_review", {}), result.usage.model_dump())
        extra_usage.append(result.usage.model_dump())
        revised.update({r["finding_id"]:r["supervisory_comment"] for r in result.data.get("comments",[])})
    accepted = 0
    for row, source in zip(suspect,evidence):
        candidate = {**row,"supervisory_comment":revised.get(source["finding_id"],"")}
        candidate.pop('_supervisory_comment_basis', None)
        if usable_narrative(candidate):
            row["supervisory_comment"] = usable_narrative(candidate)
            row['_supervisory_comment_basis'] = narrative_basis(row)
            row['student_comment'] = row['supervisory_comment']
            accepted += 1
            for stored in [*((review.get("internal_issue_ledger") or {}).get("findings",[])), *review.get("academic_findings",[])]:
                if stored.get("finding_id") and stored.get("finding_id") == row.get("finding_id"):
                    stored["supervisory_comment"] = row["supervisory_comment"]
                    stored['_supervisory_comment_basis'] = row['_supervisory_comment_basis']
    review["comment_quality_audit"] = {**comment_variation_audit(actionable),
        "prose_repair_status":"completed", "accepted_revisions":accepted,
        "requested_revisions":len(suspect), "usage":result.usage.model_dump(), "usage_records":extra_usage,
        "remaining_comments_without_valid_narrative":sum(not usable_narrative(r) for r in actionable)}
    return review
