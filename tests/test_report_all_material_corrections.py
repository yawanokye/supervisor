from io import BytesIO

from docx import Document

from app.report_exporter import build_docx_report


def test_summary_report_lists_all_material_section_corrections():
    findings = []
    for index in range(1, 6):
        findings.append({
            "finding_id": f"F{index}",
            "section": "Statement of the Problem",
            "item": f"Issue {index}",
            "severity": "major" if index < 3 else "moderate",
            "status": "partly_meets_requirement",
            "required_action": f"Required correction number {index}.",
            "comment": f"Comment {index}.",
            "evidence": [{"chapter_number": 1, "paragraph": index}],
        })

    review = {
        "summary": {
            "filename": "Chapter One.docx",
            "document_label": "Chapter 1",
            "academic_level": "Research Masters / MPhil",
            "research_approach": "quantitative",
            "review_depth": "standard",
            "academic_sections_reviewed": 1,
            "readiness_label": "Major revision required",
            "readiness_meaning": "Revise all material issues.",
            "critical_issues": 0,
            "major_issues": 2,
            "moderate_issues": 3,
            "selected_chapter": 1,
            "current_chapters_detected": [1],
        },
        "overall_academic_assessment": "The chapter requires revision.",
        "academic_strengths": [],
        "academic_section_reviews": [{
            "heading": "Statement of the Problem",
            "section_assessment": "The section requires revision.",
            "section_score": 45,
            "coverage_warning": "",
        }],
        "academic_findings": findings,
        "priority_actions": [],
        "alignment_results": [],
        "revision_results": [],
    }

    document = Document(BytesIO(build_docx_report(review)))
    table = next(
        table for table in document.tables
        if len(table.columns) == 4
        and table.rows
        and table.rows[0].cells[0].text == "No."
    )
    rows = [
        row for row in table.rows[1:]
        if "Statement of the Problem" in row.cells[1].text
    ]
    assert [row.cells[0].text for row in rows] == ["1", "2", "3", "4", "5"]
    text = "\n".join(row.cells[3].text for row in rows)
    for index in range(1, 6):
        assert f"Required correction number {index}" in text
