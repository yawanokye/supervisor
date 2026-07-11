from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id, source_section

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
        "text": clean_text(row.get("text", ""))[:1200],
        "heading": row.get("heading"),
        "section_reference": source_section(row),
        "section_number": row.get("section_number"),
        "page": row.get("page"),
        "paragraph": row.get("paragraph"),
        "paragraph_id": paragraph_id(row),
        "chapter_number": row.get("chapter_number"),
        "source_kind": row.get("source_kind", "paragraph"),
        "table_index": row.get("table_index"),
        "table_number": row.get("table_number"),
        "table_title": row.get("table_title"),
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


def _value(raw: Any) -> float | None:
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _named_value(text: str, names: Sequence[str]) -> float | None:
    name = "|".join(names)
    match = re.search(rf"(?:^|[\s,(;])(?:{name})\s*(?:=|:)?\s*(-?(?:\d+(?:\.\d+)?|\.\d+))", text, flags=re.I)
    return _value(match.group(1)) if match else None


def _df_values(text: str) -> Tuple[int | None, int | None]:
    # F(2, 347) or df1=2, df2=347
    match = re.search(r"\bF\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", text, flags=re.I)
    if match:
        return int(match.group(1)), int(match.group(2))
    df1 = _named_value(text, (r"df1", r"model\s+df"))
    df2 = _named_value(text, (r"df2", r"residual\s+df"))
    return (int(df1) if df1 is not None else None, int(df2) if df2 is not None else None)


def _close(a: float, b: float, *, relative: float = 0.08, absolute: float = 0.15) -> bool:
    return abs(a - b) <= max(absolute, relative * max(abs(a), abs(b), 1.0))


def audit_statistical_consistency(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    seen = set()

    def add(kind: str, message: str, row: Dict[str, Any], *, severity: str = "major", verification: str = "verified inconsistency") -> None:
        signature = (kind, message, row.get("paragraph"), row.get("table_index"), row.get("table_row"))
        if signature in seen:
            return
        seen.add(signature)
        warnings.append({
            "kind": kind,
            "message": message,
            "severity": severity,
            "verification": verification,
            "evidence": _evidence(row),
        })

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
                add("invalid_r_squared", f"The reported R² value of {value:g} falls outside the valid 0 to 1 range.", row, severity="critical")

        for match in re.finditer(r"\bp\s*(?:value)?\s*([=<>])\s*(\d*\.?\d+)", text, flags=re.I):
            operator, raw = match.groups()
            value = _value(raw)
            if value is None:
                continue
            if value < 0 or value > 1:
                add("invalid_p_value", f"The reported p-value of {value:g} falls outside the valid 0 to 1 range.", row, severity="critical")
                continue
            says_not_significant = bool(re.search(r"\b(?:not|non)[ -]?significant\b", low))
            says_significant = "significant" in low and not says_not_significant
            if operator == "=":
                if value < 0.05 and says_not_significant:
                    add("p_value_interpretation_mismatch", "The non-significant interpretation conflicts with the reported p-value below .05.", row)
                elif value >= 0.05 and says_significant:
                    add("p_value_interpretation_mismatch", "The significant interpretation conflicts with the reported p-value of .05 or above.", row)
            elif operator == "<" and value <= 0.05 and says_not_significant:
                add("p_value_interpretation_mismatch", "The non-significant interpretation conflicts with the reported p-value threshold.", row)
            elif operator == ">" and value >= 0.05 and says_significant:
                add("p_value_interpretation_mismatch", "The significant interpretation conflicts with the reported p-value threshold.", row)

        for match in re.finditer(r"(?<!\d)(-?\d+(?:\.\d+)?)\s*%", text):
            value = _value(match.group(1))
            if value is not None and not 0 <= value <= 100:
                add("invalid_percentage", f"The reported percentage of {value:g}% falls outside the valid 0% to 100% range.", row, severity="critical")

        alpha = _named_value(text, (r"cronbach(?:'s)?\s+alpha", r"alpha", r"α"))
        if alpha is not None and not 0 <= alpha <= 1:
            add("invalid_reliability", f"The reported reliability coefficient of {alpha:g} falls outside the valid 0 to 1 range.", row, severity="critical")

        interval = re.search(
            r"(?:confidence interval|\bci\b)(?:\s+was|\s+is)?\s*[:=]?\s*[\[(]?\s*(-?(?:\d+(?:\.\d+)?|\.\d+))\s*[,;]\s*(-?(?:\d+(?:\.\d+)?|\.\d+))",
            text,
            flags=re.I,
        )
        lower = upper = None
        if interval:
            lower, upper = _value(interval.group(1)), _value(interval.group(2))
            if lower is not None and upper is not None and lower > upper:
                add("reversed_confidence_interval", "The lower confidence limit is greater than the upper confidence limit.", row, severity="critical")

        b = _named_value(text, (r"unstandardized\s+b", r"coefficient", r"estimate", r"\bb\b"))
        se = _named_value(text, (r"std\.?\s*error", r"standard\s+error", r"\bse\b"))
        t_value = _named_value(text, (r"t(?:\s*value)?" ,))
        if b is not None and se is not None and se > 0 and t_value is not None:
            expected_t = b / se
            if not _close(abs(t_value), abs(expected_t), relative=0.06, absolute=0.12):
                add(
                    "coefficient_se_t_mismatch",
                    f"The reported coefficient, standard error and t-statistic do not reconcile: B/SE is approximately {expected_t:.3f}, not {t_value:.3f}.",
                    row,
                    severity="critical",
                )
        if b is not None and lower is not None and upper is not None and not (lower - 1e-9 <= b <= upper + 1e-9):
            add("coefficient_ci_mismatch", "The reported coefficient does not fall within its stated confidence interval.", row, severity="critical")

        coefficient = re.search(r"\b(?:beta|β|coefficient|estimate|b)\s*[=:]\s*(-?(?:\d+(?:\.\d+)?|\.\d+))", text, flags=re.I)
        if coefficient:
            value = _value(coefficient.group(1))
            positive = bool(re.search(r"\bpositive(?:ly)?\b", low))
            negative = bool(re.search(r"\bnegative(?:ly)?\b", low))
            if value is not None and value < 0 and positive and not negative:
                add("coefficient_sign_interpretation_mismatch", "A negative coefficient is described as positive.", row)
            elif value is not None and value > 0 and negative and not positive:
                add("coefficient_sign_interpretation_mismatch", "A positive coefficient is described as negative.", row)

        f_value = _named_value(text, (r"f(?:\s*statistic)?",))
        if f_value is None:
            f_match = re.search(r"\bF\s*\(\s*\d+\s*,\s*\d+\s*\)\s*(?:=|:)\s*(-?(?:\d+(?:\.\d+)?|\.\d+))", text, flags=re.I)
            f_value = _value(f_match.group(1)) if f_match else None
        r2 = _named_value(text, (r"r\s*squared", r"r²", r"r2"))
        n = _named_value(text, (r"sample\s+size", r"\bn\b"))
        df1, df2 = _df_values(text)
        if f_value is not None and t_value is not None and ("simple regression" in low or df1 == 1):
            expected_f = t_value * t_value
            if not _close(f_value, expected_f, relative=0.06, absolute=0.25):
                add("simple_regression_f_t_mismatch", f"For a one-predictor test, F should approximately equal t². The reported values imply t² ≈ {expected_f:.3f}, not F = {f_value:.3f}.", row, severity="critical")
        if f_value is not None and r2 is not None and df1 and df2 and 0 <= r2 < 1:
            expected_f = (r2 / df1) / ((1 - r2) / df2)
            if not _close(f_value, expected_f, relative=0.08, absolute=0.35):
                add("r2_f_df_mismatch", f"The reported R², F and degrees of freedom do not reconcile. These values imply F ≈ {expected_f:.3f}, not {f_value:.3f}.", row, severity="critical")
        elif f_value is not None and r2 is not None and n and df1 and n > df1 + 1 and 0 <= r2 < 1:
            expected_f = (r2 / df1) / ((1 - r2) / (n - df1 - 1))
            if not _close(f_value, expected_f, relative=0.08, absolute=0.35):
                add("r2_f_n_mismatch", f"The reported R², F, sample size and predictor count do not reconcile. They imply F ≈ {expected_f:.3f}, not {f_value:.3f}.", row, severity="critical")

        frequency = _named_value(text, (r"frequency", r"count"))
        percent_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        if frequency is not None and n and percent_match and n > 0:
            pct = _value(percent_match.group(1))
            if pct is not None:
                expected_pct = 100 * frequency / n
                if not _close(pct, expected_pct, relative=0.03, absolute=0.6):
                    add("frequency_percentage_mismatch", f"The frequency, percentage and sample size do not reconcile. The values imply approximately {expected_pct:.1f}%, not {pct:.1f}%.", row)

    return warnings


def _first_row(paragraphs: Sequence[Dict[str, Any]], pattern: str) -> Dict[str, Any] | None:
    rx = re.compile(pattern, flags=re.I)
    return next((row for row in paragraphs if rx.search(clean_text(row.get("text", "")))), None)


def audit_analysis_adequacy(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify method-specific reporting omissions without pretending to recompute."""
    text = normalised("\n".join(clean_text(row.get("text", "")) for row in paragraphs))
    warnings: List[Dict[str, Any]] = []

    def add(kind: str, message: str, row: Dict[str, Any] | None, *, severity: str = "major") -> None:
        if row is None:
            return
        warnings.append({
            "kind": kind,
            "message": message,
            "severity": severity,
            "verification": "reporting omission",
            "evidence": _evidence(row),
        })

    if any(term in text for term in ("moderation", "moderating", "interaction effect", "process macro")):
        row = _first_row(paragraphs, r"moderation|moderating|interaction effect|process macro")
        if "interaction" not in text:
            add("moderation_interaction_missing", "Moderation is claimed, but the interaction term is not clearly reported.", row, severity="critical")
        if not any(term in text for term in ("conditional effect", "simple slope", "johnson neyman", "interaction plot")):
            add("moderation_probe_missing", "The moderation result is not adequately probed with conditional effects, simple slopes, a Johnson–Neyman analysis or an interaction plot, as appropriate.", row)
        if not any(term in text for term in ("change in r squared", "delta r", "r2 change", "r squared change")):
            add("moderation_increment_missing", "The additional variance explained by the interaction is not clearly reported.", row, severity="moderate")

    if any(term in text for term in ("mediation", "mediating", "indirect effect")):
        row = _first_row(paragraphs, r"mediation|mediating|indirect effect")
        if "indirect effect" not in text:
            add("mediation_indirect_effect_missing", "Mediation is claimed, but the indirect effect is not clearly reported.", row, severity="critical")
        if not any(term in text for term in ("bootstrap confidence interval", "bootstrapped confidence interval", "bootstrap ci")):
            add("mediation_bootstrap_ci_missing", "The mediation claim lacks a bootstrapped confidence interval for the indirect effect.", row)

    if any(term in text for term in ("regression", "linear model", "ordinary least squares")):
        row = _first_row(paragraphs, r"regression|linear model|ordinary least squares")
        if not any(term in text for term in ("vif", "multicollinearity", "tolerance")):
            add("regression_multicollinearity_omitted", "The regression reporting does not clearly show how multicollinearity was assessed.", row, severity="moderate")
        if not any(term in text for term in ("residual", "homoscedasticity", "heteroscedasticity", "linearity")):
            add("regression_residual_diagnostics_omitted", "The regression reporting does not clearly present the residual or model-assumption checks needed to judge adequacy.", row)
        if not any(term in text for term in ("confidence interval", " ci ", "effect size")):
            add("regression_uncertainty_omitted", "The regression results do not clearly report confidence intervals or another appropriate indication of estimation uncertainty.", row, severity="moderate")

    if any(term in text for term in ("sem", "structural equation", "pls sem", "smartpls")):
        row = _first_row(paragraphs, r"sem|structural equation|pls.?sem|smartpls")
        if not all(any(term in text for term in group) for group in (("measurement model", "factor loading"), ("structural model", "path coefficient"))):
            add("sem_models_not_separated", "The SEM/PLS-SEM reporting does not clearly separate measurement-model evidence from structural-model evidence.", row)
        if not any(term in text for term in ("ave", "average variance extracted", "htmt", "fornell larcker")):
            add("sem_validity_evidence_omitted", "Convergent and discriminant validity evidence is not clearly reported for the measurement model.", row)

    if any(term in text for term in ("thematic analysis", "themes", "coding")):
        row = _first_row(paragraphs, r"thematic analysis|themes|coding")
        if not any(term in text for term in ("participant quotation", "verbatim quotation", "respondent stated", "interviewee")):
            add("qualitative_evidence_omitted", "The qualitative findings are not clearly supported with representative participant evidence.", row)
        if not any(term in text for term in ("credibility", "dependability", "confirmability", "reflexivity", "audit trail")):
            add("qualitative_trustworthiness_omitted", "The work does not clearly demonstrate the trustworthiness procedures used to support the qualitative interpretation.", row)

    return warnings


def statistical_warnings_to_issues(statistical_review: Dict[str, Any], academic_level: Any = None) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for idx, warning in enumerate(statistical_review.get("consistency_warnings") or [], start=1):
        evidence = warning.get("evidence") or {}
        pid = evidence.get("paragraph_id")
        if not pid:
            continue
        message = clean_text(warning.get("message"))
        verification = clean_text(warning.get("verification"))
        if verification == "verified inconsistency":
            consequence = "This numerical inconsistency can invalidate the model interpretation and must be resolved against the original analysis output before the result is accepted."
            action = "Return to the original software output, confirm that all values come from the same model run, correct the table and narrative together, and retain the output for examination."
        else:
            consequence = "The omission prevents an examiner from judging whether the analysis is adequate and whether the reported conclusion is defensible."
            action = "Add the missing model-specific evidence and align the table, narrative, hypothesis decision and discussion with that evidence."
        issues.append({
            "finding_id": f"STAT-AUDIT-{warning.get('kind')}-{idx}",
            "category": "statistical_reporting_accuracy",
            "section": evidence.get("section_reference") or evidence.get("heading") or "Results and analysis",
            "issue_title": message,
            "severity": warning.get("severity") or "major",
            "confidence": 0.98 if verification == "verified inconsistency" else 0.90,
            "evidence_paragraph_ids": [pid],
            "problematic_quote": clean_text(evidence.get("text"))[:300],
            "assessment": message,
            "academic_consequence": consequence,
            "required_action": action,
            "illustrative_guidance": "For example, reproduce the estimate, standard error, test statistic, degrees of freedom, p-value, confidence interval and model summary directly from the same original output where those statistics apply.",
            "guidance_type": "statistical_verification",
            "source_verification_required": True,
            "context_guard_adjusted": False,
            "verification_status": "deterministic_statistical_audit",
            "manual_confirmation_required": verification != "verified inconsistency",
        })
    return issues


def build_statistical_review(paragraphs: Sequence[Dict[str, Any]], *, chapter_numbers: Sequence[int]) -> Dict[str, Any]:
    targets = set(chapter_numbers)
    relevant = [row for row in paragraphs if row.get("chapter_number") in targets] or list(paragraphs)
    inventory = diagnostic_inventory(relevant)
    warnings = audit_statistical_consistency(relevant) + audit_analysis_adequacy(relevant)
    return {
        "chapter_numbers": list(chapter_numbers),
        "diagnostic_inventory": inventory,
        "consistency_warnings": warnings,
        "warning_count": len(warnings),
        "verified_inconsistency_count": sum(1 for item in warnings if item.get("verification") == "verified inconsistency"),
        "reporting_omission_count": sum(1 for item in warnings if item.get("verification") == "reporting omission"),
        "note": "The audit checks internal consistency and method-specific reporting adequacy. It does not replace recomputation from raw data or original statistical output.",
    }
