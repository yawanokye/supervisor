# Test summary, V-Professor v1.9.9.30

## Release validation

- `python -m py_compile app/*.py`: passed
- `node --check app/static/app.js`: passed
- `render.yaml` YAML parsing: passed
- focused structure, routing, alignment, contamination and DOCX-safety suite: **73 passed, 2 deprecation warnings**

## Complete historical suite

- **283 passed**
- **28 failed**
- **7 warnings**

The complete-suite failure count is unchanged from the pre-update baseline. The remaining failures are legacy or obsolete expectations involving removed finding quotas, retired visible red body markers, old DeepSeek routing, old version/checkpoint strings, a missing external test document, and unrelated authentication or storage assumptions. These tests should be updated or retired separately. The focused release suite covers all v1.9.9.30 changes.

## Focused suite command

```bash
python -m pytest -q \
 tests/test_v19930_structure_quality.py \
 tests/test_doctoral_flexible_structure.py \
 tests/test_doctoral_structure_ui.py \
 tests/test_institutional_thesis_structure.py \
 tests/test_combined_chapter_review.py \
 tests/test_combined_chapter_ui.py \
 tests/test_combined_openai_pipeline_v1995.py \
 tests/test_model_router_v198.py \
 tests/test_native_comment_export_v187.py \
 tests/test_final_professional_product_v19929.py \
 tests/test_final_review_quality_v19925.py \
 tests/test_human_supervisory_editor_v19927.py \
 tests/test_supervisory_accuracy_v186.py \
 tests/test_deterministic_supervisory_checklist_v1990.py \
 tests/test_ucc_section_contract_v1998.py
```
