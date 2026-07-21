from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Sequence, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id, source_section

def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
        if coefficient and not any(term in low for term in ("interaction", "moderation", "moderating", "buffer")):
            value = _value(coefficient.group(1))
            positive = bool(re.search(r"\bpositive(?:ly)?\s+(?:effect|influence|association|relationship|coefficient|prediction)\b", low))
            negative = bool(re.search(r"\bnegative(?:ly)?\s+(?:effect|influence|association|relationship|coefficient|prediction)\b", low))
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




def _has_results_evidence(paragraphs: Sequence[Dict[str, Any]]) -> bool:
    """Return True only when a submitted results/findings section is present.

    Methods that describe planned regression, moderation or confidence intervals
    must not be treated as completed results.
    """
    for row in paragraphs:
        chapter = int(row.get("chapter_number") or 0)
        label = normalised(source_section(row) or row.get("heading") or "")
        text = normalised(row.get("text", ""))
        if chapter < 4 or not any(term in label for term in ("result", "finding", "analysis", "discussion")):
            continue
        if row.get("source_kind") == "table_row" or any(
            term in text
            for term in ("coefficient", "p value", "p-value", "r squared", "mean", "frequency", "theme", "finding")
        ):
            return True
    return False

def _first_row(paragraphs: Sequence[Dict[str, Any]], pattern: str) -> Dict[str, Any] | None:
    rx = re.compile(pattern, flags=re.I)
    return next((row for row in paragraphs if rx.search(clean_text(row.get("text", "")))), None)


def audit_analysis_adequacy(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify result-reporting omissions only when results are submitted."""
    if not _has_results_evidence(paragraphs):
        return []
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
        raw_text = "\n".join(clean_text(item.get("text", "")) for item in paragraphs).lower()
        if not (any(term in text for term in ("change in r squared", "delta r", "r2 change", "r squared change")) or re.search(r"[δ∆Δ]\s*r[²2]", raw_text)):
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

    if any(term in text for term in ("thematic analysis", "qualitative coding", "open coding", "axial coding")):
        row = _first_row(paragraphs, r"thematic analysis|qualitative coding|open coding|axial coding")
        if not any(term in text for term in ("participant quotation", "verbatim quotation", "respondent stated", "interviewee")):
            add("qualitative_evidence_omitted", "The qualitative findings are not clearly supported with representative participant evidence.", row)
        if not any(term in text for term in ("credibility", "dependability", "confirmability", "reflexivity", "audit trail")):
            add("qualitative_trustworthiness_omitted", "The work does not clearly demonstrate the trustworthiness procedures used to support the qualitative interpretation.", row)

    return warnings



def _cells(row: Dict[str, Any]) -> List[str]:
    return [clean_text(cell) for cell in clean_text(row.get("text", "")).split("|")]


def _table_groups(paragraphs: Sequence[Dict[str, Any]]) -> Dict[Any, List[Dict[str, Any]]]:
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for row in paragraphs:
        if row.get("source_kind") != "table_row" or row.get("table_index") is None:
            continue
        groups.setdefault(row.get("table_index"), []).append(row)
    for rows in groups.values():
        rows.sort(key=lambda item: (int(item.get("table_row") or 0), int(item.get("paragraph") or 0)))
    return groups


def _table_label(rows: Sequence[Dict[str, Any]]) -> str:
    first = rows[0] if rows else {}
    number = clean_text(first.get("table_number", ""))
    title = clean_text(first.get("table_title", ""))
    if number and title:
        return f"Table {number}: {title}"
    if number:
        return f"Table {number}"
    return title or "the results table"


def _number_in_cell(value: str) -> float | None:
    value = clean_text(value).replace("−", "-").replace("–", "-")
    match = re.search(r"-?(?:\d+(?:\.\d+)?|\.\d+)", value)
    return _value(match.group(0)) if match else None


def _sample_size_from_rows(rows: Sequence[Dict[str, Any]]) -> int | None:
    text = " ".join(clean_text(row.get("table_title", "")) + " " + clean_text(row.get("text", "")) for row in rows)
    match = re.search(r"\bN\s*=\s*([0-9,]+)", text, flags=re.I)
    return int(match.group(1).replace(",", "")) if match else None


def _header_key(value: str) -> str:
    original = clean_text(value)
    low = original.lower()
    if ("Δ" in original or "δ" in low) and "r" in low:
        return "delta r2"
    if "f-change" in low or "f change" in low:
        return "f change"
    raw = low.replace("r²", "r2").replace("f²", "f2")
    raw = raw.replace("β", "beta")
    return normalised(raw)


def _header_map(rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, Any] | None]:
    for row in rows:
        cells = _cells(row)
        if len(cells) < 2:
            continue
        joined = normalised(" ".join(cells))
        if any(term in joined for term in ("predictor", "item", "variable", "statement", "construct", "model")):
            return {_header_key(cell): idx for idx, cell in enumerate(cells)}, row
    return {}, None


def _column_index(headers: Dict[str, int], *terms: str) -> int | None:
    wanted = [_header_key(term) for term in terms if _header_key(term)]
    # Exact matches first. This is essential for one-letter headings such as
    # M, B, t and p, which must not match words such as Item or Predictor.
    for term in wanted:
        if term in headers:
            return headers[term]
    for header, idx in headers.items():
        for term in wanted:
            if len(term) <= 2:
                continue
            if term in header:
                return idx
    return None


def _warning(
    kind: str,
    message: str,
    row: Dict[str, Any],
    *,
    severity: str = "major",
    verification: str = "verified inconsistency",
    action: str = "",
    example: str = "",
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "message": clean_text(message),
        "severity": severity,
        "verification": verification,
        "evidence": _evidence(row),
        "required_action": clean_text(action),
        "example": clean_text(example),
    }


def audit_table_level_accuracy(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check statistical tables as complete analytical objects.

    These checks are deterministic and deliberately conservative. They identify
    arithmetic contradictions and reporting omissions visible in the thesis. They
    do not claim to reproduce the analysis from raw data.
    """
    warnings: List[Dict[str, Any]] = []
    seen = set()

    def add(item: Dict[str, Any]) -> None:
        ev = item.get("evidence") or {}
        sig = (item.get("kind"), ev.get("table_index"), ev.get("table_row"), item.get("message"))
        if sig not in seen:
            seen.add(sig)
            warnings.append(item)

    for _table_index, rows in _table_groups(paragraphs).items():
        if not rows:
            continue
        label = _table_label(rows)
        title_norm = normalised(label)
        headers, header_row = _header_map(rows)
        header_cells = _cells(header_row) if header_row else []
        n = _sample_size_from_rows(rows)

        # Descriptive tables: recompute an overall item mean when the table makes
        # the item and overall rows explicit.
        mean_idx = _column_index(headers, "m", "mean")
        if mean_idx is not None:
            item_means: List[float] = []
            overall_row = None
            overall_value = None
            for row in rows:
                cells = _cells(row)
                if row is header_row or len(cells) <= mean_idx:
                    continue
                first = normalised(cells[0]) if cells else ""
                if "overall" in first or "grand mean" in first:
                    overall_row = row
                    # Some overall rows omit the item-description column, so use
                    # the first plausible mean after the label as a fallback.
                    overall_value = None
                    if len(cells) == len(header_cells) and len(cells) > mean_idx:
                        overall_value = _number_in_cell(cells[mean_idx])
                    if overall_value is None:
                        overall_value = next((_number_in_cell(cell) for cell in cells[1:] if _number_in_cell(cell) is not None), None)
                    continue
                if re.match(r"^[a-z]{1,6}\d{1,3}$", first.replace(" ", "")):
                    value = _number_in_cell(cells[mean_idx])
                    if value is not None:
                        item_means.append(value)
            if overall_row is not None and overall_value is not None and len(item_means) >= 3:
                calculated = sum(item_means) / len(item_means)
                if abs(calculated - overall_value) > 0.05:
                    add(_warning(
                        "descriptive_overall_mean_mismatch",
                        f"{label} reports an overall mean of {overall_value:.2f}, but the displayed item means average approximately {calculated:.2f}.",
                        overall_row,
                        severity="critical",
                        action="Check whether the overall score was calculated from respondent-level composite scores or from the displayed item means. State the calculation method and correct either the table or the interpretation.",
                        example=f"If the overall score is the simple mean of the displayed items, report approximately {calculated:.2f}; if it comes from a different composite procedure, explain that procedure below the table.",
                    ))

        # Correlation tables should not be presented as tests of influence or effect.
        joined_header = normalised(" ".join(header_cells))
        if ("correlation" in title_norm or " r " in f" {joined_header} " or "r influence" in joined_header) and any(term in normalised(" ".join(clean_text(r.get("text", "")) for r in rows)) for term in ("significant influence", "significant effect")):
            anchor = next((r for r in rows if "significant influence" in normalised(r.get("text", "")) or "significant effect" in normalised(r.get("text", ""))), header_row or rows[0])
            add(_warning(
                "correlation_interpreted_as_influence",
                f"{label} reports correlation coefficients but interprets them as evidence of influence or effect.",
                anchor,
                verification="inappropriate analysis or interpretation",
                action="Describe these results as associations or relationships. Use a correctly specified regression, SEM or other justified model if the objective is to estimate predictive influence or effect.",
                example="Replace ‘significant influence’ with ‘significant negative association’ where the statistic reported is Pearson’s r.",
            ))

        # A regression table should contain enough information for the model to be
        # assessed, not relabel correlation coefficients as beta values.
        if "regression" in title_norm:
            required = {
                "b": _column_index(headers, "b", "coefficient"),
                "se": _column_index(headers, "se b", "standard error", "se"),
                "t": _column_index(headers, "t"),
                "p": _column_index(headers, "p", "p value", "sig"),
            }
            if "beta r" in joined_header or "β r" in " ".join(header_cells) or any(value is None for value in required.values()):
                add(_warning(
                    "regression_table_incomplete",
                    f"{label} is presented as a regression analysis, but it does not report a complete regression model with B, standard error, t, p and model-level statistics.",
                    header_row or rows[0],
                    verification="reporting omission",
                    action="Rebuild the table from the original regression output. Report the unstandardised coefficient, standard error, standardised coefficient where useful, t-statistic, p-value, confidence interval, R², adjusted R², F and degrees of freedom.",
                    example="Do not label a correlation coefficient as ‘β (approximately r)’. Report either a correlation table or a complete regression table, depending on the analysis actually conducted.",
                ))

        # Row-level coefficient arithmetic across table columns.
        b_idx = _column_index(headers, "b", "estimate", "coefficient")
        se_idx = _column_index(headers, "se b", "standard error", "se")
        t_idx = _column_index(headers, "t", "t value")
        ci_idx = _column_index(headers, "95 ci", "confidence interval", "ci")
        if b_idx is not None and se_idx is not None and t_idx is not None:
            for row in rows:
                if row is header_row:
                    continue
                cells = _cells(row)
                if len(cells) <= max(b_idx, se_idx, t_idx):
                    continue
                b = _number_in_cell(cells[b_idx]); se = _number_in_cell(cells[se_idx]); t = _number_in_cell(cells[t_idx])
                if b is not None and se is not None and se > 0 and t is not None:
                    expected = b / se
                    if not _close(abs(expected), abs(t), relative=0.05, absolute=0.10):
                        add(_warning(
                            "table_coefficient_se_t_mismatch",
                            f"In {label}, the coefficient, standard error and t-statistic for ‘{cells[0]}’ do not reconcile: B/SE is approximately {expected:.2f}, not {t:.2f}.",
                            row,
                            severity="critical",
                            action="Return to the same model output and correct B, SE and t together. Do not adjust one value in isolation.",
                            example=f"For ‘{cells[0]}’, verify the row directly against the coefficients table generated by the statistical software.",
                        ))
                if ci_idx is not None and len(cells) > ci_idx and b is not None:
                    nums = re.findall(r"-?(?:\d+(?:\.\d+)?|\.\d+)", cells[ci_idx].replace("−", "-"))
                    if len(nums) >= 2:
                        lo, hi = float(nums[0]), float(nums[1])
                        if lo > hi or not (lo - 1e-9 <= b <= hi + 1e-9):
                            add(_warning(
                                "table_coefficient_ci_mismatch",
                                f"In {label}, the coefficient for ‘{cells[0]}’ does not fall within the reported confidence interval.",
                                row,
                                severity="critical",
                                action="Verify the coefficient and both confidence limits from the same model output and correct the table and narrative together.",
                                example=f"The interval reported for ‘{cells[0]}’ should contain the corresponding unstandardised coefficient B.",
                            ))

        # Model-summary consistency from wide regression tables.
        if header_row and n:
            r2_idx = _column_index(headers, "r²", "r2", "r squared")
            f_idx = _column_index(headers, "f", "f statistic")
            if r2_idx is not None and f_idx is not None:
                summary_row = next((r for r in rows if r is not header_row and len(_cells(r)) > max(r2_idx, f_idx) and _number_in_cell(_cells(r)[r2_idx]) is not None and _number_in_cell(_cells(r)[f_idx]) is not None), None)
                if summary_row:
                    cells = _cells(summary_row)
                    r2 = _number_in_cell(cells[r2_idx]); fval = _number_in_cell(cells[f_idx])
                    predictors = [r for r in rows if r is not header_row and _cells(r) and normalised(_cells(r)[0]) not in {"constant", "intercept"} and len(_cells(r)) > max(b_idx or 0, t_idx or 0)]
                    k = max(1, len(predictors))
                    if r2 is not None and fval is not None and 0 <= r2 < 1 and n > k + 1:
                        expected = (r2 / k) / ((1 - r2) / (n - k - 1))
                        if not _close(fval, expected, relative=0.08, absolute=0.50):
                            add(_warning(
                                "table_r2_f_n_mismatch",
                                f"{label} reports R² = {r2:.2f} and F = {fval:.2f} for N = {n} with {k} predictor{'s' if k != 1 else ''}, but these values imply F of approximately {expected:.2f}.",
                                summary_row,
                                severity="critical",
                                action="Rebuild the model summary from the original output and ensure that R², adjusted R², F, model degrees of freedom, residual degrees of freedom and sample size all come from the same model run.",
                                example="Copy the complete model summary and ANOVA values from one output rather than combining values from different analyses.",
                            ))

        # Model summaries displayed vertically, common in PROCESS-style output.
        row_by_name = {_header_key(_cells(r)[0]): r for r in rows if _cells(r)}
        r2_row = next((r for key, r in row_by_name.items() if key in {"r2", "r²", "r squared"}), None)
        f_row = next((r for key, r in row_by_name.items() if key == "f" or key.startswith("f(") or key.startswith("f df")), None)
        if r2_row and f_row:
            r2_cells = _cells(r2_row); f_cells = _cells(f_row)
            r2 = _number_in_cell(r2_cells[1]) if len(r2_cells) > 1 else None
            f_text = " ".join(f_cells[1:])
            fm = re.search(r"F\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*=\s*([0-9.]+)", f_text, flags=re.I)
            if r2 is not None and fm and 0 <= r2 < 1:
                df1, df2, fval = int(fm.group(1)), int(fm.group(2)), float(fm.group(3))
                expected = (r2 / df1) / ((1 - r2) / df2)
                if not _close(fval, expected, relative=0.08, absolute=0.50):
                    add(_warning(
                        "vertical_model_r2_f_df_mismatch",
                        f"{label} reports R² = {r2:.2f} and F({df1}, {df2}) = {fval:.2f}, but these values imply F of approximately {expected:.2f}.",
                        f_row,
                        severity="critical",
                        action="Verify the model summary against the original PROCESS or regression output and correct R², F and degrees of freedom as one set.",
                        example="Report the model summary exactly as it appears for the same step of the moderation model.",
                    ))
            f2_row = next((r for key, r in row_by_name.items() if "cohen" in key and "f2" in key), None)
            if f2_row and r2 is not None and 0 <= r2 < 1:
                f2_cells = _cells(f2_row); f2 = _number_in_cell(f2_cells[1]) if len(f2_cells) > 1 else None
                expected_f2 = r2 / (1 - r2)
                if f2 is not None and not _close(f2, expected_f2, relative=0.10, absolute=0.08):
                    add(_warning(
                        "model_f2_mismatch",
                        f"{label} reports Cohen’s f² = {f2:.2f}, while the displayed model R² implies a whole-model f² of approximately {expected_f2:.2f}.",
                        f2_row,
                        severity="major",
                        action="Clarify whether f² refers to the whole model or to one predictor. Recalculate it using the appropriate full and reduced models and label it accurately.",
                        example="For a whole model, f² = R²/(1−R²). For one predictor, use the change between the full and reduced model R² values.",
                    ))

        # Moderation reporting and model hierarchy.
        all_text = normalised(" ".join(clean_text(r.get("text", "")) for r in rows))
        if any(term in title_norm + " " + all_text for term in ("moderating", "moderation", "interaction term")):
            interaction_rows = [r for r in rows if any(symbol in clean_text(r.get("text", "")) for symbol in ("×", "*")) or "interaction" in normalised(r.get("text", ""))]
            if interaction_rows and not any(term in all_text for term in ("conditional effect", "simple slope", "johnson neyman", "interaction plot")):
                add(_warning(
                    "moderation_not_probed",
                    f"{label} reports a significant interaction but does not show the conditional effects, simple slopes, Johnson–Neyman result or interaction plot needed to explain the moderation.",
                    interaction_rows[-1],
                    verification="reporting omission",
                    action="Probe the interaction and report how the predictor–outcome relationship changes at meaningful values of the moderator. Add an interaction plot and the relevant confidence intervals.",
                    example="Report the effect of the predictor at low, mean and high perceived support, with a confidence interval and a plot showing the direction of the interaction.",
                ))
            # Three-way moderation must preserve model hierarchy.
            if any("between" in title_norm and "and" in title_norm and "interaction" in title_norm for _ in [0]) or any("ci aee" in normalised(r.get("text", "")) for r in rows):
                terms = [normalised(_cells(r)[0]) for r in rows if _cells(r)]
                has_xy = any("ci aee" in term for term in terms)
                has_xz = any("ci pas" in term for term in terms)
                has_yz = any("aee pas" in term for term in terms)
                has_xyz = any(all(x in term for x in ("ci", "aee", "pas")) for term in terms)
                if has_xy and (not has_xz or not has_yz or not has_xyz):
                    anchor = interaction_rows[-1] if interaction_rows else rows[-1]
                    missing = []
                    if not has_xz: missing.append("CI × PAS")
                    if not has_yz: missing.append("AEE × PAS")
                    if not has_xyz: missing.append("CI × AEE × PAS")
                    add(_warning(
                        "three_way_moderation_hierarchy_incomplete",
                        f"{label} does not report the complete hierarchical specification required for a three-way interaction. Missing or unclear terms: {', '.join(missing)}.",
                        anchor,
                        severity="critical",
                        verification="inappropriate analysis or interpretation",
                        action="Refit or re-report the model with all three main effects, all three two-way interactions and the three-way interaction. Use standard interaction labels and report the model-change statistics.",
                        example="The coefficient table should include CI, AEE, PAS, CI×AEE, CI×PAS, AEE×PAS and CI×AEE×PAS before interpreting moderated moderation.",
                    ))
                if any("pas ci aee interaction" in term or "pas ci aee" in term for term in terms):
                    anchor = next(r for r in rows if "PAS" in clean_text(r.get("text", "")) and "interaction" in clean_text(r.get("text", "")))
                    add(_warning(
                        "nonstandard_three_way_term_label",
                        f"{label} uses a non-standard expression for the three-way interaction, making the model difficult to verify.",
                        anchor,
                        verification="reporting omission",
                        action="Label the three-way term explicitly and consistently as the product of the three variables, and use the same label in the methods, table, interpretation and hypothesis decision.",
                        example="Use ‘Classroom Incivility × Academic Entitlement × Perceived Academic Support’ rather than ‘PAS × (CI + AEE interaction)’. ",
                    ))

        # Incremental F test for a single added interaction in a wide
        # moderation table. The full-model denominator degrees of freedom are
        # inferred from N and the number of reported non-constant terms.
        if header_row and n and any(term in title_norm + " " + all_text for term in ("moderating", "moderation", "interaction term")):
            r2_idx = _column_index(headers, "r2", "r squared")
            dr2_idx = _column_index(headers, "delta r2", "change in r squared", "r2 change")
            fchange_idx = _column_index(headers, "f change", "fchange")
            if r2_idx is not None and dr2_idx is not None and fchange_idx is not None:
                interaction_row = next((
                    r for r in rows
                    if r is not header_row
                    and ("interaction" in normalised(r.get("text", "")) or "×" in clean_text(r.get("text", "")))
                    and len(_cells(r)) > max(r2_idx, dr2_idx, fchange_idx)
                    and _number_in_cell(_cells(r)[r2_idx]) is not None
                    and _number_in_cell(_cells(r)[dr2_idx]) is not None
                    and _number_in_cell(_cells(r)[fchange_idx]) is not None
                ), None)
                if interaction_row:
                    cells = _cells(interaction_row)
                    if len(cells) > max(r2_idx, dr2_idx, fchange_idx):
                        r2 = _number_in_cell(cells[r2_idx]); dr2 = _number_in_cell(cells[dr2_idx]); fchange = _number_in_cell(cells[fchange_idx])
                        k_full = len([r for r in rows if r is not header_row and _cells(r) and normalised(_cells(r)[0]) not in {"constant", "intercept"}])
                        if None not in (r2, dr2, fchange) and 0 <= r2 < 1 and n > k_full + 1 and k_full >= 1:
                            expected = dr2 / ((1 - r2) / (n - k_full - 1))
                            if not _close(fchange, expected, relative=0.10, absolute=0.75):
                                add(_warning(
                                    "moderation_fchange_mismatch",
                                    f"{label} reports ΔR² = {dr2:.2f} and F-change = {fchange:.2f}, but with N = {n} and the displayed full model these values imply F-change of approximately {expected:.2f}.",
                                    interaction_row,
                                    severity="critical",
                                    action="Verify the full and reduced model summaries from the same moderation output. Correct ΔR², F-change, degrees of freedom and the interaction decision together.",
                                    example="For one newly added interaction, the F-change should reconcile with the change in R² and the residual variance of the full model.",
                                ))

        # A one-degree-of-freedom interaction has F-change equal to t squared.
        if header_row and any(term in title_norm + " " + all_text for term in ("moderating", "moderation", "interaction term")):
            t_idx_local = _column_index(headers, "t", "t value")
            fchange_idx = _column_index(headers, "f change", "fchange")
            if t_idx_local is not None and fchange_idx is not None:
                for row in rows:
                    if row is header_row or not ("interaction" in normalised(row.get("text", "")) or "×" in clean_text(row.get("text", ""))):
                        continue
                    cells = _cells(row)
                    if len(cells) <= max(t_idx_local, fchange_idx):
                        continue
                    tval = _number_in_cell(cells[t_idx_local]); fchange = _number_in_cell(cells[fchange_idx])
                    if tval is not None and fchange is not None and not _close(fchange, tval * tval, relative=0.10, absolute=0.75):
                        add(_warning(
                            "interaction_t_fchange_mismatch",
                            f"In {label}, the interaction t-statistic and F-change do not reconcile. For a one-parameter interaction, t² is approximately {tval*tval:.2f}, not {fchange:.2f}.",
                            row,
                            severity="critical",
                            action="Check that the interaction coefficient table and the model-change table come from the same model step and sample.",
                            example="For one added interaction term, the squared t-statistic should equal the corresponding one-degree-of-freedom F-change apart from rounding.",
                        ))

        # PLS-SEM/SEM measurement quality checks from explicit table labels.
        if any(term in title_norm + " " + all_text for term in ("outer loading", "factor loading", "composite reliability", "average variance extracted", "htmt", "fornell larcker", "variance inflation factor", "model fit")):
            for row in rows:
                cells = _cells(row)
                row_text = normalised(row.get("text", ""))
                if not cells:
                    continue
                if "loading" in joined_header and len(cells) >= 2 and row is not header_row:
                    loading_idx = _column_index(headers, "outer loading", "loading", "factor loading")
                    val = _number_in_cell(cells[loading_idx]) if loading_idx is not None and len(cells) > loading_idx else None
                    if val is not None and val < 0.708:
                        add(_warning(
                            "low_indicator_loading",
                            f"In {label}, the loading for ‘{cells[0]}’ is {val:.3f}, below the commonly used .708 benchmark.",
                            row,
                            verification="likely inconsistency",
                            action="Evaluate the indicator’s reliability and content validity. Explain whether it was retained or removed and show the effect of that decision on composite reliability and AVE.",
                            example="Do not delete an indicator automatically; justify the decision using its loading, construct coverage and the measurement-model results.",
                        ))
                if "htmt" in title_norm:
                    nums = [_number_in_cell(c) for c in cells[1:]]
                    for val in [v for v in nums if v is not None]:
                        if val > 0.90:
                            add(_warning(
                                "htmt_threshold_exceeded",
                                f"In {label}, an HTMT value of {val:.3f} exceeds the .90 guideline, indicating a possible discriminant-validity problem.",
                                row,
                                severity="critical",
                                action="Identify the construct pair, report the bootstrapped HTMT confidence interval where available and reconsider whether the constructs are empirically distinct.",
                                example="Name the two constructs associated with the value and avoid concluding that discriminant validity is established until the problem is resolved.",
                            ))
                if "vif" in title_norm or "variance inflation factor" in title_norm:
                    nums = [_number_in_cell(c) for c in cells[1:]]
                    for val in [v for v in nums if v is not None]:
                        if val > 5:
                            add(_warning(
                                "vif_threshold_exceeded",
                                f"In {label}, a VIF value of {val:.2f} exceeds 5 and indicates potentially serious collinearity.",
                                row,
                                severity="critical",
                                action="Check the affected predictors or indicators, investigate redundancy and report the remedial decision before interpreting the structural paths.",
                                example="Identify the exact construct or indicator with the high VIF rather than reporting only a general statement that collinearity was acceptable.",
                            ))
            # Reliability and convergent-validity columns.
            ave_idx = _column_index(headers, "ave", "average variance extracted")
            cr_idx = _column_index(headers, "composite reliability", "cr")
            alpha_idx = _column_index(headers, "cronbach alpha", "alpha")
            rhoa_idx = _column_index(headers, "rho a", "rhoa")
            for row in rows:
                if row is header_row:
                    continue
                cells = _cells(row)
                construct = cells[0] if cells else "the construct"
                for idx_value, key, low_limit, high_limit in (
                    (ave_idx, "AVE", 0.50, 1.0),
                    (cr_idx, "composite reliability", 0.70, 0.95),
                    (alpha_idx, "Cronbach’s alpha", 0.70, 0.95),
                    (rhoa_idx, "rho_A", 0.70, 0.95),
                ):
                    if idx_value is None or len(cells) <= idx_value:
                        continue
                    val = _number_in_cell(cells[idx_value])
                    if val is None:
                        continue
                    if val < low_limit:
                        add(_warning(
                            f"{key.lower().replace(' ', '_')}_below_threshold",
                            f"In {label}, {construct} has {key} = {val:.3f}, below the expected minimum of {low_limit:.2f}.",
                            row,
                            severity="critical" if key == "AVE" else "major",
                            action="Review the affected indicators and construct specification, then report and justify any remedial decision using the same measurement model.",
                            example=f"Do not conclude that {construct} has adequate {'convergent validity' if key == 'AVE' else 'internal consistency'} until the reported value meets the justified criterion or the limitation is addressed.",
                        ))
                    elif key != "AVE" and val > high_limit:
                        add(_warning(
                            f"{key.lower().replace(' ', '_')}_too_high",
                            f"In {label}, {construct} has {key} = {val:.3f}, above .95, which may indicate redundant indicators.",
                            row,
                            verification="likely inconsistency",
                            action="Check whether the indicators are excessively similar and assess whether the construct retains adequate content coverage.",
                            example="Inspect indicator wording and inter-item correlations before removing any item.",
                        ))

            # Fornell-Larcker: each diagonal square root of AVE should exceed
            # its correlations with other constructs.
            if "fornell larcker" in title_norm and header_row:
                constructs = [_header_key(cell) for cell in header_cells[1:]]
                for row in rows:
                    if row is header_row:
                        continue
                    cells = _cells(row)
                    if len(cells) < 3:
                        continue
                    row_key = _header_key(cells[0])
                    if row_key not in constructs:
                        continue
                    diag_pos = constructs.index(row_key) + 1
                    if len(cells) <= diag_pos:
                        continue
                    diag = _number_in_cell(cells[diag_pos])
                    if diag is None:
                        continue
                    for col_pos, other_key in enumerate(constructs, start=1):
                        if col_pos == diag_pos or len(cells) <= col_pos:
                            continue
                        corr = _number_in_cell(cells[col_pos])
                        if corr is not None and abs(corr) > diag + 1e-6:
                            add(_warning(
                                "fornell_larcker_violation",
                                f"In {label}, the correlation between {cells[0]} and {header_cells[col_pos]} ({corr:.3f}) exceeds the diagonal value for {cells[0]} ({diag:.3f}).",
                                row,
                                severity="critical",
                                action="Do not conclude that discriminant validity is established. Recheck the measurement model, construct distinctiveness and the corresponding HTMT evidence.",
                                example="Report the exact construct pair that fails the criterion and explain whether respecification is theoretically defensible.",
                            ))

            # Common approximate SRMR benchmark.
            if "model fit" in title_norm or "srmr" in all_text:
                for row in rows:
                    cells = _cells(row)
                    if cells and "srmr" in normalised(cells[0]):
                        val = next((_number_in_cell(cell) for cell in cells[1:] if _number_in_cell(cell) is not None), None)
                        if val is not None and val > 0.08:
                            add(_warning(
                                "srmr_above_threshold",
                                f"In {label}, SRMR = {val:.3f}, above the commonly used .08 benchmark.",
                                row,
                                severity="major",
                                action="Interpret model fit cautiously, verify the estimator-specific criterion and investigate model misspecification before accepting the structural conclusions.",
                                example="Report the exact SRMR criterion used and avoid describing the fit as good without qualification.",
                            ))

            if "q2predict" in all_text or "q2 predict" in all_text:
                if not any(term in all_text for term in ("linear model benchmark", "lm benchmark", "naive benchmark", "prediction error comparison")):
                    add(_warning(
                        "q2predict_benchmark_missing",
                        f"{label} interprets Q²predict or prediction errors without a clear comparison with an appropriate benchmark model.",
                        rows[-1],
                        verification="reporting omission",
                        action="Compare RMSE or MAE for the PLS model with the corresponding benchmark prediction errors and state the predictive conclusion using that comparison.",
                        example="A positive Q²predict value alone is not enough to claim strong out-of-sample predictive performance.",
                    ))

    return warnings


def audit_analysis_appropriateness(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check whether the stated analysis matches the stated research task."""
    warnings: List[Dict[str, Any]] = []
    text = normalised("\n".join(clean_text(row.get("text", "")) for row in paragraphs))
    objectives = [row for row in paragraphs if any(term in normalised(source_section(row)) for term in ("objective", "research question", "hypoth"))]
    results_anchor = _first_row(paragraphs, r"results|findings|analysis")

    if any(term in text for term in ("cross sectional", "cross-sectional")) and any(term in text for term in ("causal effect", "causes", "caused", "determine the effect", "impact of")):
        anchor = next((row for row in objectives if any(term in normalised(row.get("text", "")) for term in ("effect", "impact", "cause"))), results_anchor)
        if anchor:
            warnings.append(_warning(
                "causal_language_exceeds_design",
                "The study uses causal language even though the stated cross-sectional design can ordinarily establish association or prediction rather than causation.",
                anchor,
                verification="inappropriate analysis or interpretation",
                action="Use associational or predictive wording unless the study includes and justifies a credible causal identification strategy.",
                example="Write ‘is associated with’ or ‘significantly predicts’ instead of ‘causes’ or ‘has an effect on’ for an ordinary cross-sectional survey.",
            ))

    # Objectives about levels or extent require descriptive evidence.
    if any(any(term in normalised(row.get("text", "")) for term in ("level of", "extent of", "prevalence")) for row in objectives):
        if not any(term in text for term in ("mean", "standard deviation", "frequency", "percentage", "descriptive statistics")):
            anchor = objectives[0] if objectives else results_anchor
            if anchor:
                warnings.append(_warning(
                    "descriptive_analysis_missing_for_level_objective",
                    "An objective asks about a level, extent or prevalence, but the study does not clearly report the descriptive analysis needed to answer it.",
                    anchor,
                    verification="reporting omission",
                    action="Report the appropriate frequencies, percentages, means or distributional summaries and state the interpretation rule used.",
                    example="For a Likert-scale level, state how the composite score was calculated and how the cut-off points for low, moderate or high were determined.",
                ))

    # Group-comparison objectives need an appropriate comparison procedure.
    if any(any(term in normalised(row.get("text", "")) for term in ("difference", "compare", "varies by")) for row in objectives):
        if not any(term in text for term in ("t test", "anova", "ancova", "manova", "chi square", "nonparametric")):
            anchor = next((row for row in objectives if any(term in normalised(row.get("text", "")) for term in ("difference", "compare", "varies by"))), results_anchor)
            if anchor:
                warnings.append(_warning(
                    "comparison_test_not_clear",
                    "The study includes a group-comparison objective, but the analysis used to test the difference is not clearly reported.",
                    anchor,
                    verification="reporting omission",
                    action="Name and justify the comparison test, report its assumptions and provide the test statistic, degrees of freedom, p-value, effect size and confidence interval where appropriate.",
                    example="Use an independent-samples t-test for two independent groups or ANOVA for more than two groups only when the assumptions and data structure support that choice.",
                ))

    if _has_results_evidence(paragraphs) and any(term in text for term in ("moderating role", "moderates", "moderation")) and not any(term in text for term in ("interaction term", " x ", "×")):
        anchor = _first_row(paragraphs, r"moderating role|moderates|moderation")
        if anchor:
            warnings.append(_warning(
                "moderation_analysis_not_demonstrated",
                "The submitted results claim moderation, but the product interaction term is not clearly reported.",
                anchor,
                severity="critical",
                verification="inappropriate analysis or interpretation",
                action="Report the interaction model, including all constituent main effects and the interaction term, then probe any significant interaction.",
                example="For X moderated by W, report X, W and X×W in the same model before interpreting the moderating effect.",
            ))

    return warnings


def audit_measurement_structure(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Audit measurement maps, reliability tables and scale reporting.

    The checks are generic and evidence-led. They compare item counts stated in
    the methods chapter with item ranges printed in results tables, identify blank
    reliability evidence, and detect duplicate table numbers. They do not infer a
    preferred scale structure when the study does not provide one.
    """
    warnings: List[Dict[str, Any]] = []
    seen = set()

    def add(kind: str, message: str, row: Dict[str, Any], *, severity: str = "major", verification: str = "reporting omission", action: str = "") -> None:
        sig = (kind, message) if kind in {"measurement_item_allocation_mismatch", "measurement_dimension_not_reported"} else (kind, row.get("paragraph"), message)
        if sig in seen:
            return
        seen.add(sig)
        warnings.append({
            "kind": kind,
            "message": clean_text(message),
            "severity": severity,
            "verification": verification,
            "evidence": _evidence(row),
            "required_action": clean_text(action),
        })

    # Item-count declarations such as “Entitled Expectations subscale comprises 5 items”.
    declared: Dict[str, Tuple[int, Dict[str, Any], str]] = {}
    declaration_patterns = (
        re.compile(r"(?P<label>[A-Za-z][A-Za-z'’\- ]{2,70}?)\s+subscale\s+(?:comprises|contains|consists\s+of|has)\s+(?P<count>\d+)\s+items?", re.I),
        re.compile(r"(?P<count>\d+)[-\s]item\s+(?P<label>[A-Za-z][A-Za-z'’\- ]{2,70}?)\s+subscale", re.I),
    )
    for row in paragraphs:
        text = clean_text(row.get("text", ""))
        for rx in declaration_patterns:
            for match in rx.finditer(text):
                label = normalised(match.group("label"))
                label = re.sub(r"\bthe\b|\btotal\b", " ", label)
                label = re.sub(r"\s+", " ", label).strip()
                if label:
                    declared[label] = (int(match.group("count")), row, re.sub(r"^The\s+", "", clean_text(match.group("label")), flags=re.I))

    # Results/table labels such as “Entitled Expectations (AEE 1–8)”.
    range_rx = re.compile(r"(?P<label>[A-Za-z][A-Za-z'’\- ]{2,70}?)\s*\([A-Z]{2,8}\s*1\s*[–—-]\s*(?P<count>\d+)\)", re.I)
    for row in paragraphs:
        if row.get("source_kind") != "table_row":
            continue
        text = clean_text(row.get("text", ""))
        for match in range_rx.finditer(text):
            result_label = normalised(match.group("label"))
            result_count = int(match.group("count"))
            best = None
            for label, value in declared.items():
                if label in result_label or result_label in label:
                    best = (label, value)
                    break
            if best and best[1][0] != result_count:
                expected, method_row, display = best[1]
                add(
                    "measurement_item_allocation_mismatch",
                    f"The methods chapter states that {display} contains {expected} items, but the results table labels the subscale as items 1–{result_count}.",
                    row,
                    severity="critical",
                    verification="verified inconsistency",
                    action="Confirm the original instrument and final item map, correct the subscale allocation, recompute the composite scores and regenerate every affected table and model.",
                )

    # Reliability tables with blank or placeholder pilot/main-study coefficients.
    for _idx, rows in _table_groups(paragraphs).items():
        if not rows:
            continue
        title = normalised(_table_label(rows))
        header_map, header_row = _header_map(rows)
        if "reliability" not in title and not any("reliability" in key for key in header_map):
            continue
        pilot_idx = _column_index(header_map, "pilot testing reliability", "pilot reliability", "main study reliability")
        if pilot_idx is None:
            continue
        for row in rows:
            if row is header_row:
                continue
            cells = _cells(row)
            value = cells[pilot_idx] if pilot_idx < len(cells) else ""
            if normalised(value) in {"", "none", "na", "n a"} or value.strip() in {".", "-", "—"}:
                add(
                    "measurement_reliability_value_missing",
                    f"{_table_label(rows)} leaves the pilot or main-study reliability coefficient blank for {cells[0] if cells else 'a reported scale'}.",
                    row,
                    verification="reporting omission",
                    action="Insert the actual coefficient, sample size, scale or subscale name and decision from the original reliability output. Do not describe the reliability as satisfactory while the table is blank.",
                )

    # Duplicate table numbers within the same chapter.
    table_numbers: Dict[Tuple[Any, str], Tuple[str, Dict[str, Any]]] = {}
    for _idx, rows in _table_groups(paragraphs).items():
        if not rows:
            continue
        first = rows[0]
        number = clean_text(first.get("table_number"))
        title = clean_text(first.get("table_title"))
        key = (first.get("chapter_number"), number)
        if not number:
            continue
        if key in table_numbers and normalised(table_numbers[key][0]) != normalised(title):
            add(
                "duplicate_table_number",
                f"Table {number} is used for more than one table in the same chapter.",
                first,
                verification="verified inconsistency",
                action="Renumber the tables sequentially and update every in-text cross-reference, list of tables and caption field.",
            )
        else:
            table_numbers[key] = (title, first)

    # A frequency/severity scale should report both dimensions when both are used.
    methods_text = normalised(" ".join(clean_text(row.get("text", "")) for row in paragraphs if row.get("chapter_number") == 3))
    result_table_text = normalised(" ".join(
        clean_text(row.get("table_title", "")) + " " + clean_text(row.get("text", ""))
        for row in paragraphs if row.get("chapter_number") == 4 and row.get("source_kind") == "table_row"
    ))
    if "frequency subscale" in methods_text and "severity subscale" in methods_text and result_table_text:
        if "classroom incivility" in result_table_text and "severity" not in result_table_text:
            row = next((item for item in paragraphs if item.get("chapter_number") == 4 and item.get("source_kind") == "table_row" and "classroom incivility" in normalised(item.get("text", "") + " " + item.get("table_title", ""))), None)
            if row:
                add(
                    "measurement_dimension_not_reported",
                    "The methods chapter defines separate frequency and severity subscales, but the results tables report the frequency dimension without a corresponding severity result.",
                    row,
                    verification="reporting omission",
                    action="Report both dimensions and state clearly which score enters each regression or other inferential model. If severity was not analysed, explain and justify that decision before interpreting an overall construct score.",
                )

    return warnings


def statistical_warnings_to_issues(statistical_review: Dict[str, Any], academic_level: Any = None) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for idx, warning in enumerate(statistical_review.get("consistency_warnings") or [], start=1):
        evidence = warning.get("evidence") or {}
        pid = evidence.get("paragraph_id")
        if not pid:
            continue
        message = clean_text(warning.get("message"))
        verification = clean_text(warning.get("verification")) or "reporting omission"
        if verification == "verified inconsistency":
            consequence = "The values cannot all be correct as reported. This must be resolved before the result or hypothesis decision can be accepted."
            default_action = "Check the original software output, confirm that the values come from the same model run, and correct the table, narrative and conclusion together."
        elif verification == "inappropriate analysis or interpretation":
            consequence = "The analysis or interpretation does not adequately answer the research task and may lead to an invalid conclusion."
            default_action = "Use the analysis and interpretation appropriate to the research objective and data, then revise the table, hypothesis decision and discussion consistently."
        elif verification == "likely inconsistency":
            consequence = "The reported result raises a technical concern that should be resolved before the analysis is treated as reliable."
            default_action = "Verify the result against the original analytical output and explain the methodological decision clearly."
        else:
            consequence = "The missing information prevents the reader from judging whether the analysis and conclusion are adequate."
            default_action = "Add the missing model-specific evidence and align the table, narrative, hypothesis decision and discussion with it."
        issues.append({
            "finding_id": f"STAT-AUDIT-{warning.get('kind')}-{idx}",
            "category": (
                "analysis_appropriateness"
                if verification == "inappropriate analysis or interpretation"
                else "measurement_and_scoring"
                if str(warning.get("kind") or "").startswith(("measurement_", "duplicate_table_number"))
                else "statistical_accuracy"
            ),
            "section": evidence.get("section_reference") or evidence.get("heading") or "Results and analysis",
            "issue_title": message,
            "severity": warning.get("severity") or "major",
            "confidence": 0.99 if verification == "verified inconsistency" else 0.93,
            "evidence_paragraph_ids": [pid],
            "problematic_quote": clean_text(evidence.get("text"))[:420],
            "assessment": message,
            "academic_consequence": consequence,
            "required_action": clean_text(warning.get("required_action")) or default_action,
            "illustrative_guidance": clean_text(warning.get("example")),
            "guidance_type": "statistical_verification",
            "source_verification_required": True,
            "context_guard_adjusted": False,
            "verification_status": verification,
            "manual_confirmation_required": verification != "verified inconsistency",
            "table_number": evidence.get("table_number"),
            "table_title": evidence.get("table_title"),
            "table_row": evidence.get("table_row"),
        })
    return issues

def build_statistical_review(paragraphs: Sequence[Dict[str, Any]], *, chapter_numbers: Sequence[int]) -> Dict[str, Any]:
    targets = set(chapter_numbers)
    relevant = [row for row in paragraphs if row.get("chapter_number") in targets] or list(paragraphs)
    inventory = diagnostic_inventory(relevant)
    warnings = (
        audit_statistical_consistency(relevant)
        + (audit_table_level_accuracy(relevant) if _env_enabled("VPROF_STATISTICAL_TABLE_AUDIT", True) else [])
        + audit_analysis_adequacy(relevant)
        + (audit_measurement_structure(relevant) if _env_enabled("VPROF_MEASUREMENT_AUDIT", True) else [])
        + (audit_analysis_appropriateness(relevant) if _env_enabled("VPROF_ANALYSIS_APPROPRIATENESS_AUDIT", True) else [])
    )
    # Remove exact duplicates while preserving the first, usually most local, anchor.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for warning in warnings:
        evidence = warning.get("evidence") or {}
        signature = (warning.get("kind"), evidence.get("paragraph_id"), normalised(warning.get("message", "")))
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(warning)
    warnings = deduped
    kinds = {item.get("kind") for item in warnings}
    if kinds & {"table_r2_f_n_mismatch", "vertical_model_r2_f_df_mismatch"}:
        warnings = [item for item in warnings if item.get("kind") not in {"r2_f_df_mismatch", "r2_f_n_mismatch"}]
    if "moderation_not_probed" in {item.get("kind") for item in warnings}:
        warnings = [item for item in warnings if item.get("kind") != "moderation_probe_missing"]
    return {
        "chapter_numbers": list(chapter_numbers),
        "diagnostic_inventory": inventory,
        "consistency_warnings": warnings,
        "warning_count": len(warnings),
        "verified_inconsistency_count": sum(1 for item in warnings if item.get("verification") == "verified inconsistency"),
        "reporting_omission_count": sum(1 for item in warnings if item.get("verification") == "reporting omission"),
        "note": "The audit checks internal consistency and method-specific reporting adequacy. It does not replace recomputation from raw data or original statistical output.",
    }
