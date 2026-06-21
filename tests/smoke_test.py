"""Run with: python tests/smoke_test.py /path/to/sample.docx"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai_config import HybridAIConfig
from app.annotated_exporter import build_annotated_docx
from app.hybrid_ai_engine import enrich_review_with_hybrid_ai
from app.report_exporter import build_docx_report
from app.review_engine import analyse


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Provide a sample DOCX path.")
    source = Path(sys.argv[1])
    data = source.read_bytes()
    review = analyse(
        data,
        source.name,
        academic_level="Research Masters / MPhil",
        research_approach="quantitative",
        selected_chapter=1,
        review_scope="chapter",
        document_type="chapter_one",
    )
    runtime = review.pop("_runtime_context")
    review = asyncio.run(enrich_review_with_hybrid_ai(
        review,
        runtime,
        requested_mode="local",
        config=HybridAIConfig.from_env(),
    ))
    assert review["summary"]["official_rules_checked"] > 0
    assert build_docx_report(review)
    assert build_annotated_docx(data, review)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
