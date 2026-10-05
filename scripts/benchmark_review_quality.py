"""Local labelled-case checks, plus optional metrics for a saved review JSON.

No model calls. Human judgements must be recorded independently.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.statistical_math import recomputed_test_p_mismatch
from app.supervisory_voice import comment_variation_audit


def benchmark(review_path=None):
    cases = [
        ('rounded t agreement','t(28) = 2.048, p = .050',False),
        ('incorrect t probability','t(28) = 2.048, p < .001',True),
        ('rounded F agreement','F(2, 97) = 3.09, p = .05',False),
        ('incorrect chi-square decision','chi-square(1) = 10.83, p > .05',True),
        ('one-sided test requires its declared tail','One-tailed t(28) = 2.048, p = .025',False),
        ('bootstrap requires its own reference distribution','Bootstrap t(28) = 2.048, p = .02',False),
    ]
    results=[{'case':label,'expected_warning':expected,'actual_warning':bool(recomputed_test_p_mismatch(text))}
        for label,text,expected in cases]
    output={'scope':'Six labelled synthetic statistical cases, not an evaluation of live AI review quality',
        'passed':sum(r['expected_warning']==r['actual_warning'] for r in results),'total':len(results),'cases':results}
    if review_path:
        review=json.loads(Path(review_path).read_text())
        output['comment_metrics']=comment_variation_audit(review.get('canonical_findings') or [])
        output['human_review_required']='Score accuracy, evidence, actionability and voice using REVIEW_QUALITY_CHECK.md.'
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',help='Path to a saved review JSON, for descriptive comment metrics')
    args=parser.parse_args()
    result=benchmark(args.review)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed']==result['total'] else 1)
