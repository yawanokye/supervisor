from __future__ import annotations

import io
import zipfile

from docx import Document

from app.annotated_exporter import ANNOTATION_EXPORT_VERSION, build_annotated_docx, native_comment_count
from app.document_parser import extract_docx


def _docx_bytes(document: Document) -> bytes:
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _visible_content(document: Document):
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    tables = [
        [[cell.text for cell in row.cells] for row in table.rows]
        for table in document.tables
    ]
    return paragraphs, tables


def test_annotations_are_native_word_comments_and_body_is_unchanged():
    document = Document()
    document.add_heading("CHAPTER FOUR", level=1)
    document.add_heading("4.2 Regression Results", level=2)
    target = document.add_paragraph(
        "The coefficient is statistically significant, holding all other variables constant."
    )
    document.add_paragraph("Table 4.1 Regression estimates")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Variable"
    table.cell(0, 1).text = "Coefficient"
    table.cell(1, 0).text = "E-sourcing"
    table.cell(1, 1).text = "0.42"
    source = _docx_bytes(document)

    rows = extract_docx(source)
    paragraph_evidence = next(
        row for row in rows
        if "holding all other variables constant" in row.get("text", "")
    )
    table_evidence = next(
        row for row in rows
        if row.get("source_kind") == "table_row" and row.get("table_row") == 2
    )
    review = {
        "summary": {"reviewer_name": "Anokye Mohammed Adam"},
        "academic_findings": [
            {
                "status": "partly_meets_requirement",
                "section": "4.2 Regression Results",
                "section_reference": "4.2 Regression Results",
                "required_action": (
                    "Remove the claim that other variables were held constant because "
                    "the reported model contains only one predictor."
                ),
                "problematic_quote": "holding all other variables constant",
                "evidence": [{**paragraph_evidence, "document_role": "current"}],
                "annotation_eligible": True,
            },
            {
                "status": "partly_meets_requirement",
                "section": "4.2 Regression Results",
                "section_reference": "4.2 Regression Results",
                "required_action": "Interpret the coefficient and report its uncertainty.",
                "problematic_quote": "",
                "evidence": [{**table_evidence, "document_role": "current"}],
                "annotation_eligible": True,
            },
        ]
    }

    before = Document(io.BytesIO(source))
    annotated_bytes = build_annotated_docx(source, review)
    after = Document(io.BytesIO(annotated_bytes))

    assert ANNOTATION_EXPORT_VERSION == "1.9.8.8-supervisory-comment-quality"
    assert _visible_content(after) == _visible_content(before)
    assert target.text in _visible_content(after)[0]
    assert len(list(after.comments)) == 2
    comments = list(after.comments)
    comment_text = "\n".join(comment.text for comment in comments)
    assert all(comment.author == "Anokye Mohammed Adam" for comment in comments)
    assert all(comment.initials == "AMA" for comment in comments)
    assert "Remove the claim" in comment_text
    assert "Table 4.1: Regression estimates" in comment_text
    assert all("Supervisor comment" not in paragraph.text for paragraph in after.paragraphs)
    assert "SUPERVISOR REVIEW NOTES" not in "\n".join(paragraph.text for paragraph in after.paragraphs)
    assert 'w:val="C00000"' not in after.element.xml
    assert 'w:val="008000"' not in after.element.xml
    assert "w:commentRangeStart" in after.element.body.xml

    with zipfile.ZipFile(io.BytesIO(annotated_bytes)) as package:
        names = set(package.namelist())
        assert "word/comments.xml" in names
        assert "word/_rels/document.xml.rels" in names


def test_unplaced_feedback_uses_document_level_native_comment_not_inserted_notes():
    document = Document()
    document.add_paragraph("Original title")
    document.add_paragraph("Original body text remains unchanged.")
    source = _docx_bytes(document)

    review = {
        "summary": {"reviewer_name": "Dr Priscilla Boafowaa Oppong"},
        "academic_findings": [
            {
                "status": "does_not_meet_requirement",
                "section": "A section that is not present",
                "section_reference": "A section that is not present",
                "required_action": "Add the required section and explain its purpose.",
                "problematic_quote": "",
                "evidence": [],
                "headings": ["A section that is not present"],
                "annotation_eligible": True,
            }
        ]
    }

    before = Document(io.BytesIO(source))
    after = Document(io.BytesIO(build_annotated_docx(source, review)))

    assert _visible_content(after) == _visible_content(before)
    comments = list(after.comments)
    assert len(comments) == 1
    assert comments[0].author == "Dr Priscilla Boafowaa Oppong"
    assert comments[0].initials == "DPBO"
    assert "Document-level review note" in comments[0].text
    assert "Add the required section" in comments[0].text
    assert "SUPERVISOR REVIEW NOTES" not in "\n".join(p.text for p in after.paragraphs)


def test_explicit_comment_author_overrides_review_metadata():
    document = Document()
    document.add_paragraph("Text requiring review.")
    source = _docx_bytes(document)
    rows = extract_docx(source)
    evidence = next(row for row in rows if "requiring review" in row.get("text", ""))
    review = {
        "summary": {"reviewer_name": "Stored Reviewer"},
        "academic_findings": [{
            "status": "partly_meets_requirement",
            "section": "Body",
            "section_reference": "Body",
            "required_action": "Clarify this statement.",
            "problematic_quote": "requiring review",
            "evidence": [{**evidence, "document_role": "current"}],
            "annotation_eligible": True,
        }],
    }
    output = Document(io.BytesIO(build_annotated_docx(
        source, review, "Anokye Mohammed Adam"
    )))
    comments = list(output.comments)
    assert len(comments) == 1
    assert comments[0].author == "Anokye Mohammed Adam"
    assert comments[0].initials == "AMA"
