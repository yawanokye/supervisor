from pathlib import Path


def test_doctoral_structure_guidance_is_visible():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "custom chapter numbers, order and titles" in html
    assert 'id="scopeStructureHelp"' in html


def test_doctoral_upload_workflow_mentions_custom_structure():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "custom chapter numbers, order and titles" in js
    assert "Choose the complete doctoral thesis" in js


def test_ai_prompt_does_not_force_five_chapters_for_doctorates():
    prompt = Path("app/ai_prompts.py").read_text(encoding="utf-8")
    assert "do not require a fixed five-chapter sequence" in prompt
    assert "article-based" in prompt
    assert "practice-based" in prompt
