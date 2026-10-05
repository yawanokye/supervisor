"""Evidence-led statistical profiles. A model name is never inferred from a substring."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


def model_family(text: str) -> str:
    low = str(text).lower().replace('−', '-').replace('-', ' ')
    for family, pattern in (
        ('pls_sem', r'\b(?:pls\s*sem|smartpls|partial least squares)\b'),
        ('sem', r'\b(?:sem|structural equation|path analysis)\b'),
        ('logistic', r'\b(?:logistic|logit|probit|odds ratio)\b'),
        ('count', r'\b(?:poisson|negative binomial|incidence rate)\b'),
        ('multilevel', r'\b(?:multilevel|mixed effects|hierarchical linear)\b'),
        ('panel', r'\b(?:panel|fixed effects|random effects|time series|ardl|gmm)\b'),
        ('ols', r'\b(?:ols|ordinary least squares|linear regression|multiple regression|simple regression)\b'),
    ):
        if re.search(pattern, low):
            return family
    return 'unspecified'


def declared_alpha(text: str, default: float = .05) -> float:
    patterns = (
        r'(?:significance\s+(?:level|threshold)|alpha|α)\s*(?:of|was|is|=|:)\s*(\.\d+|0\.\d+)',
        r'(\.\d+|0\.\d+)\s+(?:level of significance|significance level)',
        r'(\d+(?:\.\d+)?)\s*%\s+(?:significance level|level of significance)',
    )
    for index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.I):
            if 'cronbach' in text[max(0, match.start()-25):match.start()].lower():
                continue
            value = float(match.group(1)) / (100 if index == 2 else 1)
            if 0 < value < 1:
                return value
    return default


def study_statistical_profile(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    methods = '\n'.join(str(r.get('text') or '') for r in rows if
        r.get('chapter_number') == 3 or re.search(r'method|analysis|decision rule', str(r.get('heading') or ''), re.I))
    all_text = '\n'.join(str(r.get('text') or '') for r in rows)
    return {
        'model_family': model_family(methods or all_text),
        'significance_threshold': declared_alpha(methods or all_text),
        'threshold_source': 'declared' if declared_alpha(methods or all_text, -1) > 0 else 'default .05, confirm if unspecified',
        'robust_or_bootstrap': bool(re.search(r'\b(?:robust|bootstrap|clustered)\b', methods, re.I)),
        'scope': 'internal consistency, not independent raw-data reproduction',
    }


def claim_clauses(text: str) -> list[str]:
    return [s.strip() for s in re.split(r';|(?<!\d)\.(?!\d)|\.(?=\s+[A-Z])|\b(?:while|whereas)\b|,\s*but\b', text) if s.strip()]


def rounding_tolerance(raw: str) -> float:
    value = str(raw).strip()
    decimals = len(value.split('.', 1)[1]) if '.' in value else 0
    return .5 * 10 ** -decimals
