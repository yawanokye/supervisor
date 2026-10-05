"""Conservative arithmetic checks with explicit rounding and test assumptions."""
from __future__ import annotations

import re
from scipy import stats
from .statistical_profile import rounding_tolerance


def rounded_ratio_matches(b_raw: str, se_raw: str, t_raw: str, *, absolute_statistic=False) -> bool:
    raw = [re.search(r"-?(?:\d+(?:\.\d+)?|\.\d+)",str(v).replace("−","-")) for v in (b_raw,se_raw,t_raw)]
    if not all(raw): return True
    b,se,t = [float(v.group()) for v in raw]
    db,ds,dt = [rounding_tolerance(v.group()) for v in raw]
    if se-ds <= 0: return True
    possible = [(b+sign*db)/(se+other*ds) for sign in (-1,1) for other in (-1,1)]
    if absolute_statistic:
        low = 0 if min(possible) <= 0 <= max(possible) else min(abs(v) for v in possible)
        high = max(abs(v) for v in possible); t = abs(t)
    else:
        low,high = min(possible),max(possible)
    return t+dt >= low and t-dt <= high


def recomputed_test_p_mismatch(text: str) -> str:
    """Only explicit t(df), F(df1,df2) and chi²(df), with one exact p claim."""
    if re.search(r"one[ -](?:tailed|sided)|bootstrap|permutation|adjusted p|corrected p",text,re.I): return ""
    p = list(re.finditer(r"\bp\s*([=<>])\s*(0?\.\d+|1(?:\.0+)?)",text,re.I))
    tests = list(re.finditer(r"\b(t|F|chi(?:[- ]?square(?:d)?)?|χ²)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)\s*=\s*(-?(?:\d+(?:\.\d+)?|\.\d+))",text,re.I))
    if len(p) != 1 or len(tests) != 1: return ""
    test = tests[0]; family = test.group(1).lower(); d1=int(test.group(2)); d2=int(test.group(3) or 0)
    raw=test.group(4); value=float(raw); delta=rounding_tolerance(raw)
    if d1 <= 0: return ""
    if family == "t" and not d2:
        sf=lambda x: 2*stats.t.sf(abs(x),d1)
    elif family == "f" and d2 > 0 and value >= 0:
        sf=lambda x: stats.f.sf(max(0,x),d1,d2)
    elif family.startswith(("chi","χ")) and not d2 and value >= 0:
        sf=lambda x: stats.chi2.sf(max(0,x),d1)
    else: return ""
    computed=[float(sf(value-delta)),float(sf(value+delta)),float(sf(value))]
    lo,hi=min(computed),max(computed); operator=p[0].group(1); reported=float(p[0].group(2)); dp=rounding_tolerance(p[0].group(2))
    mismatch = ((operator == "=" and reported != 0 and (reported+dp < lo or reported-dp > hi))
        or (operator == "<" and lo >= reported) or (operator == ">" and hi <= reported))
    if not mismatch: return ""
    return f"The reported {test.group(1)} test and degrees of freedom imply p approximately {sf(value):.4g}, inconsistent with p {operator} {reported:g} even allowing for displayed rounding. Verify the test specification and original output."
