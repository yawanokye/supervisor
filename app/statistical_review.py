from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from .document_parser import clean_text, normalised

DIAGNOSTIC_GROUPS = {
    "general_regression_assumptions": [
        "normality", "linearity", "homoscedasticity", "heteroscedasticity",
        "multicollinearity", "vif", "variance inflation factor", "tolerance",
        "independence of errors", "residual", "durbin watson",
    ],
    "time_series_or_panel_diagnostics": [
        "stationarity", "unit root", "adf", "phillips perron", "cointegration",
        "serial correlation", "autocorrelation", "cross sectional dependence",
        "hausman", "breusch pagan", "pesaran", "lag selection", "stability test",
    ],
    "sem_or_measurement_diagnostics": [
        "measurement model", "structural model", "model fit", "cfi", "tli",
        "rmsea", "srmr", "chi square", "average variance extracted", "ave",
        "composite reliability", "htmt", "fornell larcker", "factor loading",
    ],
    "survey_bias_and_data_quality": [
        "common method bias", "harman", "missing data", "outlier",
        "mahalanobis", "response bias",
    ],
    "model_specification_and_robustness": [
        "model specification", "goodness of fit", "r squared", "adjusted r squared",
        "robust standard errors", "endogeneity", "instrumental variable",
        "sensitivity analysis", "robustness check",
    ],
}


def _evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": clean_text(row.get("text", ""))[:900],
        "heading": row.get("heading"),
        "section_number": row.get("section_number"),
        "page": row.get("page"),
        "paragraph": row.get("paragraph"),
        "chapter_number": row.get("chapter_number"),
        "source_kind": row.get("source_kind", "paragraph"),
        "table_index": row.get("table_index"),
        "table_row": row.get("table_row"),
    }


def diagnostic_inventory(paragraphs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    text = "\n".join(normalised(row.get("text", "")) for row in paragraphs)
    groups = {
        name: sorted({term for term in terms if normalised(term) in text})
        for name, terms in DIAGNOSTIC_GROUPS.items()
    }
    return {
        "groups": groups,
        "any_diagnostics_present": any(groups.values()),
        "diagnostic_group_count": sum(1 for hits in groups.values() if hits),
    }


def _value(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def audit_statistical_consistency(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    seen = set()

    def add(kind: str, message: str, row: Dict[str, Any]) -> None:
        signature = (kind, message, row.get("paragraph"), row.get("table_index"), row.get("table_row"))
        if signature in seen:
            return
        seen.add(signature)
        warnings.append({"kind": kind, "message": message, "evidence": _evidence(row)})

    for row in paragraphs:
        text = clean_text(row.get("text", ""))
        low = normalised(text)
        if not text:
            continue

        for match in re.finditer(
            r"\b(?:r[-\s]?(?:squared|2)|r²|r2|adjusted\s+r[-\s]?(?:squared|2)|adjusted\s+r²)"
            r"\s*[=:]?\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.I,
        ):
            value = _value(match.group(1))
            if value is not None and not 0 <= value <= 1:
                add("invalid_r_squared", f"An R-squared value of {value:g} falls outside the valid 0 to 1 range.", row)

        for match in re.finditer(r"\bp\s*(?:value)?\s*([=<>])\s*(\d*\.?\d+)", text, flags=re.I):
            operator, raw = match.groups()
            value = _value(raw)
            if value is None:
                continue
            if value < 0 or value > 1:
                add("invalid_p_value", f"A reported p-value of {value:g} falls outside the valid 0 to 1 range.", row)
                continue
            says_not_significant = bool(re.search(r"\b(?:not|non)[ -]?significant\b", low))
            says_significant = "significant" in low and not says_not_significant
            if operator == "=":
                if value < 0.05 and says_not_significant:
                    add("p_value_interpretation_mismatch", "The non-significant interpretation conflicts with a p-value below 0.05.", row)
                elif value >= 0.05 and says_significant:
                    add("p_value_interpretation_mismatch", "The significant interpretation conflicts with a p-value of 0.05 or above.", row)
            elif operator == "<" and value <= 0.05 and says_not_significant:
                add("p_value_interpretation_mismatch", "The non-significant interpretation conflicts with the reported p-value threshold.", row)
            elif operator == ">" and value >= 0.05 and says_significant:
                add("p_value_interpretation_mismatch", "The significant interpretation conflicts with the reported p-value threshold.", row)

        for match in re.finditer(r"(?<!\d)(-?\d+(?:\.\d+)?)\s*%", text):
            value = _value(match.group(1))
            if value is not None and not 0 <= value <= 100:
                add("invalid_percentage", f"A percentage of {value:g}% falls outside the valid 0% to 100% range.", row)

        interval = re.search(
            r"(?:confidence interval|ci)(?:\s+was|\s+is)?\s*[:=]?\s*[\[(]?\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.I,
        )
        if interval:
            lower, upper = _value(interval.group(1)), _value(interval.group(2))
            if lower is not None and upper is not None and lower > upper:
                add("reversed_confidence_interval", "The lower confidence-limit value is greater than the upper limit.", row)

        coefficient = re.search(r"\b(?:beta|β|coefficient|estimate|b)\s*[=:]\s*(-?\d+(?:\.\d+)?)", text, flags=re.I)
        if coefficient:
            value = _value(coefficient.group(1))
            positive = bool(re.search(r"\bpositive(?:ly)?\b", low))
            negative = bool(re.search(r"\bnegative(?:ly)?\b", low))
            if value is not None and value < 0 and positive and not negative:
                add("coefficient_sign_interpretation_mismatch", "A negative coefficient is described as positive.", row)
            elif value is not None and value > 0 and negative and not positive:
                add("coefficient_sign_interpretation_mismatch", "A positive coefficient is described as negative.", row)

    return warnings


def build_statistical_review(paragraphs: Sequence[Dict[str, Any]], *, chapter_numbers: Sequence[int]) -> Dict[str, Any]:
    targets = set(chapter_numbers)
    relevant = [row for row in paragraphs if row.get("chapter_number") in targets] or list(paragraphs)
    inventory = diagnostic_inventory(relevant)
    warnings = audit_statistical_consistency(relevant)
    return {
        "chapter_numbers": list(chapter_numbers),
        "diagnostic_inventory": inventory,
        "consistency_warnings": warnings,
        "warning_count": len(warnings),
        "note": "Internal consistency screening does not replace recomputation from raw data or original statistical output.",
    }
