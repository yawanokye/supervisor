from pathlib import Path


def test_summary_is_defined_before_degree_contract_rescue():
    source = Path('app/academic_ai_engine.py').read_text()
    marker = 'required_categories = _degree_required_public_categories'
    idx = source.index(marker)
    prior = source[max(0, idx - 700):idx]
    assert 'summary = review.get("summary") or {}' in prior
    assert 'if not isinstance(summary, dict):' in prior
