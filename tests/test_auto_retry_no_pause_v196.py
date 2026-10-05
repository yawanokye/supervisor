from pathlib import Path


def test_transient_failures_queue_instead_of_pause():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert 'status="queued"' in source
    assert "_queue_automatic_retry(" in source
    assert 'record.status = "queued"' in source
    transient_block = source[source.index("except ExternalAssessmentValidationError"):source.index("finally:", source.index("except ExternalAssessmentValidationError"))]
    assert 'status="paused"' not in transient_block
    assert "retrying automatically" in transient_block.lower() or "automatically" in transient_block.lower()


def test_resume_preserves_paid_input_hashes():
    academic = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    external = Path("app/external_assessment.py").read_text(encoding="utf-8")
    for source in (academic, external):
        assert '"retry_generation": int(retry_generation or 0)' not in source
        assert '"regeneration_generation"' in source


def test_last_mile_expert_rescue_prevents_empty_annotation_output():
    source = Path("app/academic_ai_engine.py").read_text(encoding="utf-8")
    assert "direct_grounded_comment_rescue" in source
    assert "direct_expert_rescue" in source
    assert "no factual, correctly placed" in source


def test_native_and_inline_annotation_bundle_remains_required():
    source = Path("app/main.py").read_text(encoding="utf-8")
    exporter = Path("app/annotated_exporter.py").read_text(encoding="utf-8")
    inline = Path("app/inline_annotated_exporter.py").read_text(encoding="utf-8")
    assert "native_annotation_audit" in source
    assert "inline_annotation_audit" in source
    assert "annotation_bundle_validation_passed" in source
    assert "document.add_comment" in exporter
    assert "2.11.0-verified-placement-native" in exporter
    assert "2.11.0-verified-placement-inline" in inline
