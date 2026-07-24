from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

from app.main import _review_time_estimate


def test_success_path_does_not_call_first_twice():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert ".first()\n                .first()" not in source


def test_export_stage_has_short_local_eta():
    record = SimpleNamespace(
        started_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
        estimated_pages=20, review_depth="advanced", current_stage="document-export",
        progress=98, status="processing",
    )
    result = _review_time_estimate(record)
    assert 10 <= result["estimated_seconds_remaining"] <= 240
    assert result["estimated_completion_at"]


def test_status_endpoint_exposes_eta_fields():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert "estimated_seconds_remaining" in source
    assert "estimated_completion_at" in source
    assert "response.update(timing)" in source

def test_export_reuses_individually_saved_artifacts():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert "load_annotated, review_id" in source
    assert "load_inline_annotated, review_id" in source
    assert "Native Word comments completed; preparing the inline document" in source
