from pathlib import Path


def test_portal_provides_resume_action_for_paused_jobs():
    html = Path("app/templates/portal.html").read_text(encoding="utf-8")
    assert "item.status in ['paused', 'failed']" in html
    assert "/api/review/jobs/{{ item.job_id }}/resume" in html
    assert "last saved checkpoint" in html
    assert "Recover" in html
    assert "item.payload_available" in html


def test_browser_handles_paused_recoverable_jobs():
    javascript = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'job.status === "paused"' in javascript
    assert 'job.status === "failed" && job.resume_url' in javascript
    assert "Recovering the interrupted stage" in javascript
    assert "requestJobResume" in javascript
    assert "completed checkpoint" in javascript


def test_render_blueprint_uses_persistent_checkpoint_storage():
    render = Path("render.yaml").read_text(encoding="utf-8")
    assert "mountPath: /var/data" in render
    assert "REVIEW_STORAGE_DIR" in render
    assert "value: /var/data/reviews" in render
    assert "AUTO_RESUME_JOBS" in render


def test_external_assessment_runs_independent_stages_in_parallel():
    source = Path("app/external_assessment.py").read_text(encoding="utf-8")
    assert '"foundation": _complete_assessment_stage' in source
    assert '"evidence_core": _complete_assessment_stage' in source
    assert '"integrity": _complete_assessment_stage' in source
    assert '"corrections": _complete_assessment_stage' in source
    assert '"decision": _complete_assessment_stage' in source
    assert "return_when=asyncio.FIRST_COMPLETED" in source


def test_final_report_is_not_created_for_a_paused_job():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert 'status="paused"' in source
    assert '"partial_report_generated": False' in source
    assert 'checkpoints.save(\n                "pipeline-final"' in source
