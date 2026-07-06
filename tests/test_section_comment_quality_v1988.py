from io import BytesIO

from docx import Document

from app.annotated_exporter import build_annotated_docx, native_comment_count


def _source_doc() -> bytes:
    doc = Document()
    doc.add_heading("CHAPTER ONE", level=1)
    doc.add_heading("Background to the Study", level=2)
    doc.add_paragraph("Green procurement is discussed in general terms.")
    doc.add_heading("Statement of the Problem", level=2)
    doc.add_paragraph("The problem is not yet fully localised.")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def test_section_comments_are_specific_not_generic_stamps():
    review = {
        "summary": {"reviewer_name": "Supervisor"},
        "academic_section_reviews": [
            {
                "chapter_number": 1,
                "heading": "Background to the Study",
                "section_path": ["Background to the Study"],
                "section_assessment": "This section has been reviewed against the selected academic level.",
            },
            {
                "chapter_number": 1,
                "heading": "Statement of the Problem",
                "section_path": ["Statement of the Problem"],
                "section_assessment": "No major issues were found.",
            },
        ],
        "academic_findings": [],
        "alignment_results": [],
        "revision_results": [],
    }
    exported = build_annotated_docx(_source_doc(), review)
    assert native_comment_count(exported) == 2
    doc = Document(BytesIO(exported))
    comments = [comment.text for comment in doc.comments]
    joined = "\n".join(comments)
    assert "selected academic level" not in joined
    assert "No major issues" not in joined
    assert "reviewed against" not in joined
    assert any("broad sustainability debate" in text and "Ghanaian" in text for text in comments)
    assert any("practical problem" in text and "empirical gap" in text for text in comments)


def test_useful_model_section_assessment_is_polished_and_expanded():
    review = {
        "summary": {"reviewer_name": "Supervisor"},
        "academic_section_reviews": [
            {
                "chapter_number": 1,
                "heading": "Purpose of the study",
                "section_path": ["Purpose of the study"],
                "section_assessment": "Issue: The purpose is narrower than the objectives and should be aligned.",
            },
        ],
        "academic_findings": [],
        "alignment_results": [],
        "revision_results": [],
    }
    exported = build_annotated_docx(_source_doc(), review)
    doc = Document(BytesIO(exported))
    text = "\n".join(comment.text for comment in doc.comments)
    assert "Issue:" not in text
    assert "purpose is narrower" in text
    assert "trace the design" in text or "principal construct" in text
