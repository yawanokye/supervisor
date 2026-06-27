from pathlib import Path

def test_index_hero_copy_is_replaced():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "Meet Virtual Professor {{ user.full_name }} (V), your Academic Supervision and Assessment Assistant." in html
    assert "Academic thesis review and guidance" not in html
    assert "Meet your academic advisor for your research work" not in html
    assert "Professor provides structured, context-aware thesis review and guidance for all academic levels." not in html
