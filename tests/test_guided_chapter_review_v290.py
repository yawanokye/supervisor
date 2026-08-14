import json
from pathlib import Path

from app.guided_review import (
    guided_chapter_units,
    guided_start_index,
    latest_completed_guided_review_id,
    merge_guided_reviews,
    scoped_guided_payload,
    should_use_guided_review,
)
from app.human_comment_budget import apply_human_comment_budget
from app.statistical_review import audit_analysis_appropriateness


def test_toc_rows_do_not_become_guided_chapters():
    rows = [
        {"chapter_number": 1, "is_toc_entry": False, "document_zone": "table_of_contents"},
        {"chapter_number": 2, "is_toc_entry": True, "document_zone": "table_of_contents"},
        {"chapter_number": 1, "is_toc_entry": False, "document_zone": "main_work"},
        {"chapter_number": 2, "is_toc_entry": False, "document_zone": "main_work"},
    ]
    assert guided_chapter_units(rows) == [1, 2]
    assert should_use_guided_review(
        workflow_type="supervisory_review", review_scope="full_thesis", units=[1, 2]
    )
    assert should_use_guided_review(
        workflow_type="supervisory_review", review_scope="chapter_range", units=[1, 2]
    )
    assert should_use_guided_review(
        workflow_type="supervisory_review", review_scope="chapter", units=[1, 2]
    )
    assert not should_use_guided_review(
        workflow_type="external_assessment", review_scope="full_thesis", units=[1, 2]
    )


def test_guided_payload_reviews_one_chapter_and_retains_plan():
    payload = {"review_scope": "full_thesis", "filename": "thesis.docx"}
    scoped = scoped_guided_payload(payload, units=[1, 2, 3], current_index=1)
    assert scoped["review_scope"] == "chapter"
    assert scoped["selected_chapter"] == 2
    assert scoped["guided_current_chapter"] == 2
    assert scoped["guided_is_last"] is False
    assert scoped["original_review_scope"] == "full_thesis"


def test_supervisor_can_choose_the_guided_start_chapter():
    units = [1, 2, 3, 4, 5]
    assert guided_start_index(units, 0) == 0
    assert guided_start_index(units, 3) == 2
    assert latest_completed_guided_review_id(
        {"3": "review-three", "4": "review-four"},
        units=units,
        current_index=4,
    ) == "review-four"


def test_guided_final_review_merges_chapter_findings():
    one = {
        "review_id": "one",
        "summary": {"selected_chapter": 1, "overall_score": 70},
        "academic_findings": [{"finding_id": "a", "issue_title": "Problem A"}],
        "canonical_findings": [{"finding_id": "a", "issue_title": "Problem A"}],
    }
    two = {
        "review_id": "two",
        "summary": {"selected_chapter": 2, "overall_score": 80},
        "academic_findings": [{"finding_id": "b", "issue_title": "Problem B"}],
        "canonical_findings": [{"finding_id": "b", "issue_title": "Problem B"}],
    }
    merged = merge_guided_reviews([one, two], filename="thesis.docx")
    assert merged["review_id"] not in {"one", "two"}
    assert merged["summary"]["review_scope"] == "full_thesis"
    assert merged["summary"]["overall_score"] == 75.0
    assert {row["finding_id"] for row in merged["academic_findings"]} == {"a", "b"}


def test_human_comment_budget_groups_lower_priority_repetition():
    review = {
        "summary": {"review_scope": "chapter", "review_depth": "light"},
        "canonical_findings": [
            {
                "finding_id": f"f{index}",
                "finding_number": index,
                "severity": "minor",
                "category": "Academic writing",
                "issue_title": "The same wording problem appears here",
                "status": "partly_meets_requirement",
            }
            for index in range(1, 25)
        ],
    }
    result = apply_human_comment_budget(review)
    assert len(result["canonical_findings"]) <= 10
    assert result["deferred_issue_ledger"]["count"] >= 14
    assert result["summary"]["human_comment_budget_applied"] is True


def test_effect_is_allowed_for_regression_but_explicit_causation_is_checked():
    acceptable = [
        {
            "text": "The cross-sectional study used OLS regression. X had a positive estimated effect on Y, B = .31, p = .004.",
            "heading": "Results",
            "paragraph": 1,
        }
    ]
    assert not any(
        row["kind"] == "causal_language_exceeds_design"
        for row in audit_analysis_appropriateness(acceptable)
    )

    causal = [
        {
            "text": "The cross-sectional study used OLS regression and X caused the improvement in Y.",
            "heading": "Results",
            "paragraph": 1,
        }
    ]
    assert any(
        row["kind"] == "causal_language_exceeds_design"
        for row in audit_analysis_appropriateness(causal)
    )


def test_portal_and_api_expose_explicit_continue_action():
    source = Path("app/main.py").read_text(encoding="utf-8")
    portal = Path("app/templates/portal.html").read_text(encoding="utf-8")
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    assert '@app.post("/api/review/jobs/{job_id}/continue"' in source
    assert 'status="awaiting_continue"' in source
    assert "Continue to next chapter" in portal
    assert 'job.status === "awaiting_continue"' in javascript
    assert "requestChapterContinue" in javascript


def test_every_multichapter_supervisory_upload_is_guided_and_visible():
    source = Path("app/main.py").read_text(encoding="utf-8")
    page = Path("app/templates/index.html").read_text(encoding="utf-8")
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'if workflow_type == "supervisory_review":' in source
    assert "even when\n    # the form was left on Single chapter or Combined chapters" in source
    assert "Upgrade retained jobs created by an earlier build" in source
    assert 'id="loadingTitle"' in page
    assert 'id="guidedStage"' in page
    assert "Only this chapter is being reviewed now" in javascript
    assert 'name="guided_start_chapter"' in page
    assert "scanGuidedChapterPlan" in javascript
    assert "Each completed annotated chapter will become the working copy" in javascript
    assert "reviewing coverage packet" in source
    assert "checking the next group of paragraphs and tables" in source
    assert "latest_completed_guided_review_id" in source
    assert "native_export_source" in source


def test_database_migration_carries_guided_state():
    source = Path("app/database.py").read_text(encoding="utf-8")
    for field in (
        "guided_mode", "guided_current_index", "guided_total_units",
        "guided_units_json", "guided_review_ids_json", "guided_tokens_used",
    ):
        assert field in source
