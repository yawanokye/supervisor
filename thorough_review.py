from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .document_parser import clean_text, normalised
from .supervisory_accuracy_guard import paragraph_id, source_section


def _make_issue(
    *,
    finding_id: str,
    category: str,
    section: str,
    title: str,
    severity: str,
    confidence: float,
    evidence_ids: Sequence[str],
    quote: str,
    assessment: str,
    consequence: str,
    action: str,
    example: str = "",
) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "category": category,
        "section": clean_text(section),
        "issue_title": clean_text(title),
        "severity": severity,
        "confidence": confidence,
        "evidence_paragraph_ids": list(dict.fromkeys(evidence_ids))[:8],
        "problematic_quote": clean_text(quote)[:320],
        "assessment": clean_text(assessment),
        "academic_consequence": clean_text(consequence),
        "required_action": clean_text(action),
        "illustrative_guidance": clean_text(example),
        "guidance_type": "direct_correction",
        "source_verification_required": False,
        "context_guard_adjusted": False,
    }


def _current(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in paragraphs if row.get("document_role", "current") == "current"]


def _find_rows(
    rows: Sequence[Dict[str, Any]],
    pattern: str,
    *,
    chapters: Optional[set[int]] = None,
    section_contains: str | None = None,
) -> List[Dict[str, Any]]:
    rx = re.compile(pattern, flags=re.I)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if chapters and row.get("chapter_number") not in chapters:
            continue
        if section_contains and section_contains not in normalised(source_section(row)):
            continue
        if rx.search(clean_text(row.get("text", ""))):
            out.append(row)
    return out


def _doc_text(rows: Sequence[Dict[str, Any]], chapters: Optional[set[int]] = None) -> str:
    return "\n".join(
        clean_text(row.get("text", ""))
        for row in rows
        if not chapters or row.get("chapter_number") in chapters
    )


def _estimate_n(rows: Sequence[Dict[str, Any]]) -> Optional[int]:
    text = _doc_text(rows)
    candidates: List[int] = []
    for pat in (
        r"\bN\s*=\s*(\d{2,5})\b",
        r"\b(?:sample|respondents?|participants?|usable responses?)\s*(?:of|=|was|were|comprised|total(?:led)?\s*)?\s*(\d{2,5})\b",
        r"\b(\d{2,5})\s+(?:usable\s+)?(?:responses?|respondents?|participants?)\b",
    ):
        for m in re.finditer(pat, text, flags=re.I):
            value = int(m.group(1))
            if 20 <= value <= 100000:
                candidates.append(value)
    if not candidates:
        return None
    return Counter(candidates).most_common(1)[0][0]


def _normalise_r2(value: float) -> float:
    # Some text may extract .41 as 41. Treat values above 1 and below 100 as percentages.
    if value > 1 and value <= 100:
        return value / 100.0
    return value


def _num(raw: str) -> Optional[float]:
    raw = raw.strip()
    if raw.startswith("."):
        raw = "0" + raw
    try:
        return float(raw)
    except Exception:
        return None


def _extract_labeled_r2(text: str) -> Optional[float]:
    patterns = [
        r"(?:R\s*(?:square|squared)|R\s*²|R²|R2)\s*(?:=|:|was|is)?\s*(0?\.\d+|\d+\.\d+|\d{1,2})",
        r"coefficient of determination\s*(?:=|:|was|is)?\s*(0?\.\d+|\d+\.\d+|\d{1,2})",
    ]
    for pat in patterns:
        match = re.search(pat, text, flags=re.I)
        if match:
            value = _num(match.group(1))
            if value is not None:
                return _normalise_r2(value)
    return None


def _extract_f_df(text: str) -> Optional[Tuple[int, int, float]]:
    match = re.search(r"F\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*=\s*(\d+(?:\.\d+)?)", text, flags=re.I)
    if match:
        return int(match.group(1)), int(match.group(2)), float(match.group(3))
    return None


def _extract_table_row_r2_f(text: str) -> Optional[Tuple[float, float]]:
    """Infer R2 and F from common compact regression rows copied from Word tables.

    Example fragments often become: 'R R² Adj. R² SEest F ... Constant ... .64 .41 .40 0.60 48.92'.
    This is conservative and only fires when the header and the constant row are both present.
    """
    low = normalised(text)
    if "r²" not in text and "r2" not in low and "r square" not in low:
        return None
    if "constant" not in low or " f " not in f" {low} ":
        return None
    # After 'Constant', collect compact decimal/number tokens. Usually R, R2, AdjR2, SEest, F occur in order.
    tail = re.split(r"\bconstant\b", text, maxsplit=1, flags=re.I)[-1]
    nums = []
    for raw in re.findall(r"(?<![A-Za-z])(?:0?\.\d+|\d+\.\d+|\d+)(?![A-Za-z])", tail):
        value = _num(raw)
        if value is not None:
            nums.append(value)
    # Filter likely sequence: decimals <= 1 and then F > 1 after at least three model summary numbers.
    for idx in range(0, max(0, len(nums) - 4)):
        r_val, r2_val, adj_r2_val, se_val, f_val = nums[idx:idx + 5]
        if 0 <= r_val <= 1 and 0 <= r2_val <= 1 and 0 <= adj_r2_val <= 1 and f_val > 1:
            return r2_val, f_val
    return None


def _add_r2_f_inconsistency(rows: Sequence[Dict[str, Any]], out: List[Dict[str, Any]]) -> None:
    n = _estimate_n(rows)
    chapter4 = [row for row in rows if row.get("chapter_number") == 4]
    if not chapter4:
        return
    seen = set()
    for idx, row in enumerate(chapter4):
        window_rows = chapter4[max(0, idx - 2): min(len(chapter4), idx + 3)]
        window = "\n".join(clean_text(r.get("text", "")) for r in window_rows)
        f_df = _extract_f_df(window)
        if not f_df:
            continue
        df1, df2, reported_f = f_df
        r2 = _extract_labeled_r2(window)
        table_r2_f = _extract_table_row_r2_f(window)
        if r2 is None and table_r2_f:
            r2, _ = table_r2_f
        if r2 is None:
            continue
        if not (0 < r2 < 1) or df1 <= 0 or df2 <= 0:
            continue
        expected = (r2 / df1) / ((1 - r2) / df2)
        if expected <= 0:
            continue
        relative_gap = abs(expected - reported_f) / max(expected, reported_f)
        if relative_gap < 0.15 or abs(expected - reported_f) < 5:
            continue
        signature = (df1, df2, round(r2, 3), round(reported_f, 2))
        if signature in seen:
            continue
        seen.add(signature)
        target = row
        out.append(_make_issue(
            finding_id=f"THOROUGH-R2-F-CONSISTENCY-{len(seen)}",
            category="results_and_interpretation",
            section=source_section(target),
            title="The reported R² and F-statistic do not appear internally consistent",
            severity="critical",
            confidence=0.88,
            evidence_ids=[paragraph_id(r) for r in window_rows],
            quote=clean_text(window)[:320],
            assessment=(
                f"The results appear to combine R² = {r2:.2f} with F({df1}, {df2}) = {reported_f:.2f}. For a regression model with these degrees of freedom, the reported R² would imply an F-statistic of approximately {expected:.2f}."
            ),
            consequence=(
                "This raises a serious numerical accuracy concern. An examiner may question whether the regression table, model summary, ANOVA table or narrative was copied correctly from the original statistical output."
            ),
            action=(
                "Rebuild the regression table directly from the original SPSS, PROCESS, R or Stata output. Verify R, R², adjusted R², F, degrees of freedom, t, p-values, confidence intervals and the hypothesis decision before interpreting the model."
            ),
            example=(
                "For example, if Table 7 reports R² = .41 for two predictors with df2 = 347, the F-statistic should be checked against the original ANOVA/model-summary output before the conclusion is retained."
            ),
        ))


def _table_number_issues(rows: Sequence[Dict[str, Any]], out: List[Dict[str, Any]]) -> None:
    table_hits: List[Tuple[int, Dict[str, Any], str]] = []
    for row in rows:
        text = clean_text(row.get("text", ""))
        if row.get("chapter_number") not in {3, 4, 5}:
            continue
        for m in re.finditer(r"\bTable\s+(\d{1,3})\b", text, flags=re.I):
            table_hits.append((int(m.group(1)), row, text[:180]))
    by_num: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for number, row, _ in table_hits:
        by_num[number].append(row)
    duplicate = [(num, items) for num, items in by_num.items() if len({paragraph_id(r) for r in items}) > 1]
    if duplicate:
        num, items = duplicate[0]
        target = items[0]
        out.append(_make_issue(
            finding_id=f"THOROUGH-TABLE-NUMBER-DUPLICATE-{num}",
            category="tables_figures_and_presentation",
            section=source_section(target),
            title="Table numbering appears inconsistent or duplicated",
            severity="major",
            confidence=0.85,
            evidence_ids=[paragraph_id(r) for r in items[:6]],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The thesis appears to reuse or mis-sequence a table number across methodology/results sections.",
            consequence="Incorrect table numbering makes it difficult to track results, cross-references and examiner comments, especially in Chapters Three and Four.",
            action="Renumber all tables sequentially by chapter or according to the institutional format, then update every in-text reference to match the corrected table numbers.",
            example="For example, if Chapter Three already contains Table 1, Chapter Four should not rely on inconsistent numbering or refer to a table number that does not match the displayed table.",
        ))



_METHOD_PATTERNS = {
    "correlation": r"\b(?:correlation|pearson|spearman|kendall)\b",
    "linear_regression": r"\b(?:linear regression|multiple regression|hierarchical regression|ordinary least squares|\bols\b|regression analysis)\b",
    "logistic_regression": r"\b(?:logistic regression|logit|odds ratio|binary outcome)\b",
    "anova": r"\b(?:anova|ancova|manova|analysis of variance|post hoc|tukey|bonferroni)\b",
    "t_test": r"\b(?:t[- ]test|paired samples|independent samples)\b",
    "chi_square": r"\b(?:chi[- ]square|crosstab|cross[- ]tabulation|contingency table)\b",
    "sem": r"\b(?:structural equation|\bsem\b|pls[- ]sem|amos|smartpls|measurement model|structural model)\b",
    "factor_analysis": r"\b(?:factor analysis|efa|cfa|factor loading|kmo|bartlett)\b",
    "moderation": r"\b(?:moderation|moderator|moderating|interaction effect|simple slope|conditional effect|johnson[- ]neyman|process macro)\b",
    "mediation": r"\b(?:mediation|mediator|mediating|indirect effect|bootstrapped indirect|sobel)\b",
    "panel_time_series": r"\b(?:panel data|time series|unit root|stationarity|cointegration|fixed effects|random effects|hausman|ardl|vecm|var model|gmm)\b",
    "qualitative": r"\b(?:qualitative|interview|focus group|thematic analysis|content analysis|coding|codes|theme|themes|trustworthiness|credibility|dependability|transferability|confirmability)\b",
    "mixed_methods": r"\b(?:mixed methods|mixed-methods|triangulation|convergent design|explanatory sequential|exploratory sequential|integration of findings)\b",
    "systematic_review": r"\b(?:systematic review|scoping review|meta[- ]analysis|prisma|inclusion criteria|exclusion criteria|screening)\b",
    "experimental": r"\b(?:experiment|quasi[- ]experimental|control group|treatment group|pretest|posttest|random assignment|randomisation|randomization)\b",
}

_METHOD_LABELS = {
    "correlation": "correlation analysis",
    "linear_regression": "linear or multiple regression",
    "logistic_regression": "logistic regression",
    "anova": "ANOVA/ANCOVA/MANOVA",
    "t_test": "t-test analysis",
    "chi_square": "chi-square analysis",
    "sem": "SEM/PLS-SEM",
    "factor_analysis": "factor analysis",
    "moderation": "moderation analysis",
    "mediation": "mediation analysis",
    "panel_time_series": "panel or time-series analysis",
    "qualitative": "qualitative analysis",
    "mixed_methods": "mixed-methods analysis",
    "systematic_review": "systematic/scoping review or meta-analysis",
    "experimental": "experimental or quasi-experimental analysis",
}


def _detected_methods(rows: Sequence[Dict[str, Any]], chapters: Optional[set[int]] = None) -> set[str]:
    text = normalised(_doc_text(rows, chapters))
    detected = {
        name for name, pattern in _METHOD_PATTERNS.items()
        if re.search(pattern, text, flags=re.I)
    }

    # A phrase such as "a systematic review of established scales" inside a
    # questionnaire methodology does not make the study a systematic review.
    # Require a review-design cluster and no clear primary-data route before
    # activating PRISMA/search-screening-appraisal requirements.
    if "systematic_review" in detected:
        review_signals = sum(
            term in text
            for term in (
                "systematic review", "scoping review", "meta analysis",
                "meta-analysis", "prisma", "search strategy",
                "database search", "inclusion criteria",
                "exclusion criteria", "quality appraisal", "risk of bias",
            )
        )
        primary_signals = any(
            term in text
            for term in (
                "questionnaire", "respondents", "participants",
                "data collection", "sampling", "population",
                "spss", "stata", "regression", "survey",
                "interview", "focus group",
            )
        )
        if review_signals < 2 or primary_signals:
            detected.discard("systematic_review")
    return detected


def _has_any(text: str, terms: Sequence[str]) -> bool:
    low = normalised(text)
    return any(normalised(term) in low for term in terms)


def _rows_with_any(rows: Sequence[Dict[str, Any]], terms: Sequence[str], chapters: Optional[set[int]] = None) -> List[Dict[str, Any]]:
    pattern = r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b"
    return _find_rows(rows, pattern, chapters=chapters)


def _first_method_row(rows: Sequence[Dict[str, Any]], method: str, chapters: Optional[set[int]] = None) -> Optional[Dict[str, Any]]:
    pattern = _METHOD_PATTERNS.get(method)
    if not pattern:
        return None
    matches = _find_rows(rows, pattern, chapters=chapters)
    return matches[0] if matches else None


def _first_evidence_ids(rows: Sequence[Dict[str, Any]], *selected: Optional[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for row in selected:
        if row:
            ids.append(paragraph_id(row))
    if not ids and rows:
        ids.append(paragraph_id(rows[0]))
    return list(dict.fromkeys(ids))[:6]


def _add_if_missing(
    rows: Sequence[Dict[str, Any]],
    out: List[Dict[str, Any]],
    *,
    finding_id: str,
    method: str,
    present_chapters: set[int],
    required_terms: Sequence[str],
    title: str,
    severity: str,
    category: str,
    assessment: str,
    consequence: str,
    action: str,
    example: str,
    check_chapters: Optional[set[int]] = None,
) -> None:
    text = _doc_text(rows, check_chapters or present_chapters)
    if _has_any(text, required_terms):
        return
    target = _first_method_row(rows, method, chapters=present_chapters) or (rows[0] if rows else None)
    if not target:
        return
    out.append(_make_issue(
        finding_id=finding_id,
        category=category,
        section=source_section(target),
        title=title,
        severity=severity,
        confidence=0.82,
        evidence_ids=_first_evidence_ids(rows, target),
        quote=clean_text(target.get("text", ""))[:300],
        assessment=assessment,
        consequence=consequence,
        action=action,
        example=example,
    ))


def _add_generic_method_specific_issues(rows: Sequence[Dict[str, Any]], output: List[Dict[str, Any]]) -> None:
    """Add method-sensitive safeguards without assuming any one study design.

    The rules only fire when the document itself signals a method. They are
    framed as verification requirements because this app does not recompute the
    analysis from raw data.
    """
    ch3_4 = {3, 4}
    methods = _detected_methods(rows, ch3_4)

    if not methods:
        return

    # Regression families.
    if methods & {"linear_regression", "logistic_regression"}:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-REGRESSION-DIAGNOSTICS-MISSING",
            method="linear_regression" if "linear_regression" in methods else "logistic_regression",
            present_chapters=ch3_4,
            required_terms=("normality", "linearity", "homoscedasticity", "heteroscedasticity", "multicollinearity", "vif", "residual", "durbin", "odds ratio", "model fit", "classification"),
            title="The regression analysis needs model-appropriate diagnostics and reporting checks",
            severity="major",
            category="results_and_interpretation",
            assessment="The methods or results chapter signals regression-type analysis, but the surrounding methods/results do not clearly show the diagnostics and reporting elements required for the specific model used.",
            consequence="Without model-appropriate checks, the reader cannot judge whether the estimator, assumptions, coefficients, p-values and conclusions are defensible.",
            action="State the exact regression model, outcome type, predictors, coding, assumption checks, diagnostic thresholds, remedies for violations and the full reporting elements used for interpretation.",
            example="For example, an OLS model should normally address residual behaviour, linearity, homoscedasticity, multicollinearity and influential cases, while a logistic model should report odds ratios, model fit and classification or discrimination evidence where appropriate.",
        )

    # Correlation used as causal language.
    if "correlation" in methods:
        correlation_rows = _find_rows(rows, r"\bcorrelation\b", chapters={3, 4})
        causal_rows = _find_rows(rows, r"\b(?:influence|effect|impact|predicts?|causes?|leads to|determines?)\b", chapters={4, 5})
        if correlation_rows and causal_rows:
            target = causal_rows[0]
            output.append(_make_issue(
                finding_id="GENERIC-CORRELATION-CAUSAL-LANGUAGE",
                category="results_and_interpretation",
                section=source_section(target),
                title="Causal or predictive language may exceed a correlational analysis",
                severity="major",
                confidence=0.8,
                evidence_ids=_first_evidence_ids(rows, correlation_rows[0], target),
                quote=clean_text(target.get("text", ""))[:300],
                assessment="The document signals correlation analysis but also uses stronger causal or predictive wording in the results or discussion.",
                consequence="A correlation alone does not establish influence, effect or causation, and overstatement can weaken the defensibility of the interpretation.",
                action="Align the wording with the analysis actually conducted, or justify the stronger term by showing a regression, experimental, longitudinal or causal-identification design that supports it.",
                example="For example, if only Pearson correlation was used, write that the variables are significantly associated, rather than saying one variable influences or causes the other.",
            ))

    # ANOVA / t-test / chi-square reporting.
    if "anova" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-ANOVA-REPORTING-CHECKS",
            method="anova",
            present_chapters=ch3_4,
            required_terms=("homogeneity", "levene", "post hoc", "effect size", "eta", "partial eta", "pairwise", "assumption"),
            title="The group-comparison analysis needs assumption, post-hoc and effect-size reporting where applicable",
            severity="major",
            category="results_and_interpretation",
            assessment="ANOVA/ANCOVA/MANOVA-type analysis is signalled, but the thesis does not clearly show the required assumption checks and interpretation details for the group comparison.",
            consequence="Without homogeneity/assumption checks, post-hoc logic and effect sizes where applicable, a significant F-test may be statistically under-interpreted.",
            action="Report the exact group-comparison model, assumption checks, degrees of freedom, F-value, p-value, effect size and any post-hoc or adjusted comparisons required by the design.",
            example="For example, if three or more groups are compared, state the Levene result or relevant robustness decision, then report the post-hoc comparisons that explain where the group differences lie.",
        )

    if "t_test" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-TTEST-REPORTING-CHECKS",
            method="t_test",
            present_chapters=ch3_4,
            required_terms=("normality", "levene", "effect size", "cohen", "confidence interval", "mean difference"),
            title="The t-test reporting should show assumptions, mean difference and effect size",
            severity="moderate",
            category="results_and_interpretation",
            assessment="A t-test is signalled, but the thesis does not clearly show enough assumption and effect-size information to support the interpretation.",
            consequence="The result may be treated as merely significant or non-significant without showing magnitude, direction and confidence in the estimated difference.",
            action="Report the test type, group or paired means, mean difference, t-value, degrees of freedom, p-value, confidence interval, assumption decision and effect size.",
            example="For example, for an independent-samples t-test, include Levene’s test or the corrected degrees of freedom, then interpret the mean difference and Cohen’s d, not only the p-value.",
        )

    if "chi_square" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-CHISQUARE-REPORTING-CHECKS",
            method="chi_square",
            present_chapters=ch3_4,
            required_terms=("expected count", "cramer", "phi", "effect size", "cross-tab", "crosstab", "association"),
            title="The chi-square analysis should report cell adequacy and association strength",
            severity="moderate",
            category="results_and_interpretation",
            assessment="Chi-square analysis is signalled, but expected-cell conditions and association strength are not clearly reported in the surrounding results.",
            consequence="A chi-square p-value alone does not show whether the test assumptions are acceptable or whether the association is practically meaningful.",
            action="Report the contingency table, expected count conditions, chi-square value, degrees of freedom, p-value and an association measure such as Phi or Cramer’s V where appropriate.",
            example="For example, if several expected counts are below the acceptable threshold, use Fisher’s exact test or collapse categories where defensible, then explain the decision.",
        )

    # SEM, PLS, factor analysis.
    if "sem" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-SEM-MEASUREMENT-STRUCTURAL-CHECKS",
            method="sem",
            present_chapters=ch3_4,
            required_terms=("loading", "ave", "composite reliability", "cronbach", "htmt", "fornell", "rmsea", "srmr", "cfi", "tli", "model fit", "path coefficient", "bootstrapping"),
            title="SEM/PLS-SEM reporting should separate measurement and structural-model evidence",
            severity="critical",
            category="results_and_interpretation",
            assessment="SEM or PLS-SEM is signalled, but the thesis does not clearly present the full measurement and structural-model evidence expected for that analysis route.",
            consequence="The reader cannot judge construct validity, reliability, discriminant validity, model fit, path estimates or the credibility of the hypothesised relationships.",
            action="Report the measurement model and structural model separately, using criteria appropriate to CB-SEM or PLS-SEM rather than mixing the two without justification.",
            example="For example, PLS-SEM reporting should normally include indicator loadings, internal consistency, convergent validity, discriminant validity, collinearity, bootstrapped paths and R²/Q² or predictive assessment where applicable.",
        )

    if "factor_analysis" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-FACTOR-ANALYSIS-CHECKS",
            method="factor_analysis",
            present_chapters=ch3_4,
            required_terms=("kmo", "bartlett", "loading", "cross-loading", "eigenvalue", "variance explained", "fit", "ave", "composite reliability"),
            title="Factor-analysis reporting needs adequacy, loading and validity evidence",
            severity="major",
            category="results_and_interpretation",
            assessment="Factor analysis is signalled, but the chapter does not clearly provide the adequacy, loading and validity evidence needed to support the scale structure.",
            consequence="Weak or incomplete factor evidence makes it difficult to defend the measurement of constructs used in the results.",
            action="Report the extraction approach, rotation or estimation method, retention criteria, item loadings, problematic items, explained variance or model fit and reliability/validity decisions.",
            example="For example, if EFA was used, state KMO, Bartlett’s test, extraction method, rotation, retained factors and item loadings; if CFA was used, report fit indices and standardised loadings.",
        )

    # Mediation/moderation are conditional on being detected, not assumed.
    if "mediation" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-MEDIATION-INDIRECT-EFFECTS-MISSING",
            method="mediation",
            present_chapters=ch3_4,
            required_terms=("indirect effect", "bootstrap", "bootstrapped", "confidence interval", "sobel", "total effect", "direct effect"),
            title="Mediation analysis should report indirect effects and confidence intervals",
            severity="critical",
            category="results_and_interpretation",
            assessment="Mediation is signalled, but the surrounding results do not clearly show the indirect-effect evidence needed to establish mediation.",
            consequence="Without the indirect effect and its confidence interval, the thesis cannot support a mediation claim even if individual regression paths are significant.",
            action="Report the direct effect, indirect effect, total effect, bootstrap confidence interval and the decision rule for mediation, then align the discussion with the tested causal pathway and study design limits.",
            example="For example, say mediation is supported only when the bootstrapped confidence interval for the indirect effect excludes zero, and avoid claiming mediation from separate significant paths alone.",
        )

    if "moderation" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-MODERATION-CONDITIONAL-EFFECTS-MISSING",
            method="moderation",
            present_chapters=ch3_4,
            required_terms=("conditional effect", "simple slope", "johnson", "interaction plot", "r2 change", "r² change", "change in r", "interaction term"),
            title="Moderation analysis should explain the interaction pattern, not only the interaction p-value",
            severity="critical",
            category="results_and_interpretation",
            assessment="Moderation is signalled, but the results do not clearly report conditional effects, simple slopes, Johnson-Neyman output, R² change or an interaction plot that explains how the relationship changes across moderator levels.",
            consequence="A significant interaction coefficient alone does not show the direction, strength or practical meaning of the moderation effect.",
            action="Report the interaction coefficient, change in explained variance where applicable, conditional effects at meaningful moderator values, confidence intervals and an interaction plot or equivalent simple-slope interpretation.",
            example="For example, after testing a predictor × moderator term, state whether the predictor-outcome relationship becomes weaker, stronger or changes direction at low, average and high levels of the moderator.",
        )

    if "process macro" in normalised(_doc_text(rows, ch3_4)):
        process_rows = _find_rows(rows, r"\bPROCESS\s+(?:Macro\s+)?Model\s+\d+\b|\bPROCESS\s+Macro\b", chapters=ch3_4)
        if process_rows and not _has_any(_doc_text(rows, ch3_4), ("model number", "model 1", "model 2", "model 3", "model 4", "model 7", "model 14", "bootstrap", "confidence interval")):
            target = process_rows[0]
            output.append(_make_issue(
                finding_id="GENERIC-PROCESS-SPECIFICATION-UNCLEAR",
                category="results_and_interpretation",
                section=source_section(target),
                title="PROCESS Macro reporting should identify the exact model and required output",
                severity="major",
                confidence=0.82,
                evidence_ids=[paragraph_id(target)],
                quote=clean_text(target.get("text", ""))[:300],
                assessment="PROCESS is mentioned, but the exact model number, role of variables and required bootstrap or conditional output are not clearly reported.",
                consequence="Readers cannot verify whether the analysis matches the hypothesis structure or whether the conclusion follows from the correct PROCESS output.",
                action="State the PROCESS model number, predictor, outcome, mediator or moderator roles, number of bootstrap samples, confidence interval level and the specific output used for the decision.",
                example="For example, a mediation model should report the indirect effect and bootstrap confidence interval, while a moderation model should report the interaction and conditional effects.",
            ))

    if "mixed_methods" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-MIXED-METHODS-INTEGRATION-MISSING",
            method="mixed_methods",
            present_chapters=ch3_4,
            required_terms=("integration", "triangulation", "joint display", "merge", "connect", "explain", "meta-inference"),
            title="Mixed-methods work should show integration between strands",
            severity="major",
            category="methodological_rigour",
            assessment="Mixed-methods language is used, but the methodology/results do not clearly show how the quantitative and qualitative strands are integrated.",
            consequence="Without integration, the study may read as two parallel studies rather than one coherent mixed-methods inquiry.",
            action="State the mixed-methods design, priority, sequence, point of integration, integration procedure and how integrated findings answer the research questions.",
            example="For example, use a joint display or narrative integration to show how interview themes explain, expand or challenge the statistical results.",
        )

    if "qualitative" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-QUALITATIVE-TRUSTWORTHINESS-MISSING",
            method="qualitative",
            present_chapters=ch3_4,
            required_terms=("coding", "theme", "thematic", "credibility", "dependability", "confirmability", "transferability", "member checking", "audit trail", "inter-coder", "reflexivity", "quotation"),
            title="Qualitative analysis should show coding, theme development and trustworthiness evidence",
            severity="major",
            category="methodological_rigour",
            assessment="Qualitative analysis is signalled, but the methodology/results do not clearly show the analytic procedure and trustworthiness safeguards.",
            consequence="The reader cannot judge how the themes or interpretations were derived from the data and whether they are credible.",
            action="Describe coding stages, theme development, use of quotations, researcher reflexivity and trustworthiness procedures appropriate to the qualitative design.",
            example="For example, a thematic-analysis chapter should explain how codes were generated, how themes were refined and how participant quotations support each major theme.",
        )

    if "panel_time_series" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-PANEL-TIME-SERIES-DIAGNOSTICS-MISSING",
            method="panel_time_series",
            present_chapters=ch3_4,
            required_terms=("unit root", "stationarity", "cointegration", "serial correlation", "autocorrelation", "heteroscedasticity", "cross-sectional dependence", "hausman", "fixed effects", "random effects", "lag", "robust"),
            title="Panel or time-series analysis requires design-specific diagnostics",
            severity="critical",
            category="results_and_interpretation",
            assessment="Panel or time-series analysis is signalled, but the thesis does not clearly show the diagnostic sequence required for the data structure and estimator.",
            consequence="Ignoring time dependence, stationarity, serial correlation, heteroscedasticity, cross-sectional dependence or estimator selection can invalidate standard errors and model interpretation.",
            action="Report the data structure, estimator choice and diagnostics appropriate to the model, then show how any violations were handled before interpreting coefficients.",
            example="For example, a panel-regression chapter should justify fixed or random effects, report the Hausman or equivalent selection logic where relevant, and address heteroscedasticity or serial/cross-sectional dependence if detected.",
        )

    if "systematic_review" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-REVIEW-METHOD-TRANSPARENCY-MISSING",
            method="systematic_review",
            present_chapters=ch3_4,
            required_terms=("search strategy", "database", "inclusion criteria", "exclusion criteria", "screening", "prisma", "quality appraisal", "risk of bias", "coding"),
            title="Review-based research needs transparent search, screening and appraisal procedures",
            severity="major",
            category="methodological_rigour",
            assessment="The work signals a review-based design, but the method does not clearly provide the transparent procedure needed for reproducibility.",
            consequence="A review without search, screening and appraisal detail risks reading as a narrative summary rather than a defensible systematic or scoping review.",
            action="Report databases, search strings, date range, inclusion/exclusion criteria, screening process, appraisal approach and synthesis method.",
            example="For example, include a PRISMA-style flow or equivalent screening account showing records identified, excluded and retained for synthesis.",
        )

    if "experimental" in methods:
        _add_if_missing(
            rows, output,
            finding_id="GENERIC-EXPERIMENTAL-DESIGN-VALIDITY-CHECKS",
            method="experimental",
            present_chapters=ch3_4,
            required_terms=("random", "control group", "treatment", "pretest", "posttest", "baseline", "validity", "attrition", "manipulation check", "effect size"),
            title="Experimental or quasi-experimental results should address design validity and treatment evidence",
            severity="major",
            category="methodological_rigour",
            assessment="An experimental or quasi-experimental design is signalled, but the document does not clearly show enough information about group equivalence, treatment implementation and validity threats.",
            consequence="Without design-validity checks, the results may overstate attribution of outcomes to the intervention or treatment.",
            action="Report assignment procedure, group comparability, treatment exposure, attrition, manipulation or fidelity checks, effect sizes and limits to causal inference.",
            example="For example, if random assignment was not used, describe how baseline differences were handled and avoid claiming causal effects beyond the design evidence.",
        )


def _add_analysis_method_drift_issue(rows: Sequence[Dict[str, Any]], output: List[Dict[str, Any]]) -> None:
    """Flag unsupported drift only when methods/results appear to name different analysis routes."""
    ch3_methods = _detected_methods(rows, {3})
    ch4_methods = _detected_methods(rows, {4})
    if not ch3_methods or not ch4_methods:
        return
    # Focus on inferential/analysis families. Descriptive methods can legitimately appear everywhere.
    core = set(_METHOD_PATTERNS) - {"mixed_methods"}
    added_in_results = sorted((ch4_methods - ch3_methods) & core)
    if not added_in_results:
        return
    target_method = added_in_results[0]
    target = _first_method_row(rows, target_method, chapters={4})
    method_list = ", ".join(_METHOD_LABELS.get(m, m) for m in added_in_results[:4])
    ch3_list = ", ".join(_METHOD_LABELS.get(m, m) for m in sorted(ch3_methods)[:6])
    if target:
        output.append(_make_issue(
            finding_id=f"GENERIC-METHOD-RESULTS-ANALYSIS-DRIFT-{target_method.upper()}",
            category="cross_section_coherence",
            section=source_section(target),
            title="The results chapter introduces an analysis route not clearly planned in the methodology",
            severity="major",
            confidence=0.84,
            evidence_ids=[paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:300],
            assessment=f"Chapter Four appears to introduce {method_list}, while Chapter Three more clearly signals {ch3_list or 'a different analysis plan'}.",
            consequence="When the results use tests or models not specified in the methodology, the reader cannot assess whether the analysis was planned, justified and aligned with the objectives or hypotheses.",
            action="Reconcile Chapter Three and Chapter Four by stating every actual analysis used, the objective or hypothesis it answers, and the assumptions or reporting requirements attached to that analysis.",
            example="For example, if a moderation, mediation, SEM, ANOVA, regression or qualitative coding analysis appears in the results, Chapter Three should have already justified that exact analysis route and linked it to the relevant research question or hypothesis.",
        ))


def _add_duplicate_hypothesis_issue(rows: Sequence[Dict[str, Any]], output: List[Dict[str, Any]]) -> None:
    hits: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("chapter_number") not in {1, 3, 4, 5}:
            continue
        text = clean_text(row.get("text", ""))
        for match in re.finditer(r"\b(?:Research\s+)?Hypothes(?:is|es)\s*(\d{1,3})\b|\bH0?\s*(\d{1,3})\b|\bH1\s*(\d{1,3})\b", text, flags=re.I):
            number = next((g for g in match.groups() if g), None)
            if number:
                hits[number].append(row)
    for number, items in sorted(hits.items(), key=lambda item: int(item[0])):
        unique_items = list({paragraph_id(r): r for r in items}.values())
        if len(unique_items) <= 2:  # H0 and H1 may legitimately appear for one hypothesis.
            continue
        target = unique_items[1]
        output.append(_make_issue(
            finding_id=f"GENERIC-DUPLICATE-HYPOTHESIS-{number}",
            category="cross_section_coherence",
            section=source_section(target),
            title=f"Hypothesis {number} appears to be duplicated or difficult to trace",
            severity="major",
            confidence=0.83,
            evidence_ids=[paragraph_id(row) for row in unique_items[:6]],
            quote=clean_text(target.get("text", ""))[:260],
            assessment=f"The same hypothesis number appears in several places in a way that may not represent one clearly traceable null/alternative pair.",
            consequence="Duplicated or unclear hypothesis numbering disrupts alignment across objectives, analysis tables, hypothesis decisions and discussion subsections.",
            action="Create a clean hypothesis register and ensure each objective, hypothesis, analysis table, result decision and discussion subsection uses the same number and wording.",
            example="For example, build a table with columns for objective, research question or hypothesis, variable(s), statistical or qualitative procedure, result table and decision/conclusion.",
        ))
        break



def _add_articleready_style_generic_audit(rows: Sequence[Dict[str, Any]], output: List[Dict[str, Any]]) -> None:
    """Add report-first, ArticleReady-style method/results/discussion safeguards.

    These checks are deliberately generic. They do not assume a particular
    example study; they ask whether the thesis gives a traceable chain from
    objectives to methods, analysis, results, discussion and recommendations.
    """
    ch3_text = _doc_text(rows, {3})
    ch4_text = _doc_text(rows, {4})
    ch5_text = _doc_text(rows, {5})
    methods = _detected_methods(rows, {3, 4})
    if not (ch3_text or ch4_text):
        return

    has_objective_terms = bool(re.search(r"\b(?:objective|research question|hypothes(?:is|es))\b", _doc_text(rows, {1, 3, 4}), flags=re.I))
    has_analysis_terms = bool(methods) or bool(re.search(r"\b(?:analysis|analysed|analyzed|result|finding|table|model|test|theme|coefficient|p[- ]?value|significant)\b", ch3_text + "\n" + ch4_text, flags=re.I))
    if has_objective_terms and has_analysis_terms:
        matrix_terms = ("analysis plan", "data analysis matrix", "objective", "hypothesis", "research question", "procedure", "test", "model", "theme")
        # The presence of the words alone is not enough. This rule fires only when the methods chapter lacks an explicit matrix/register wording.
        if not _has_any(ch3_text, ("analysis matrix", "data analysis plan", "objective-by-objective", "hypothesis-by-hypothesis", "analysis-by-objective", "variable register", "model specification")):
            target = _find_rows(rows, r"\b(?:data analysis|methodology|methods|analysis)\b", chapters={3})[:1]
            if target:
                row = target[0]
                output.append(_make_issue(
                    finding_id="AR-REVIEW-METHOD-ANALYSIS-TRACEABILITY-MATRIX",
                    category="methodological_rigour",
                    section=source_section(row),
                    title="The methodology needs a clearer objective-to-analysis traceability plan",
                    severity="major",
                    confidence=0.84,
                    evidence_ids=[paragraph_id(row)],
                    quote=clean_text(row.get("text", ""))[:300],
                    assessment="The methods chapter signals data analysis, but it does not clearly present an objective-by-objective or hypothesis-by-hypothesis map showing which data, variables and analytic procedure answer each research task.",
                    consequence="Without this traceability plan, the results chapter can appear as a set of statistical or thematic outputs rather than a controlled response to the study objectives.",
                    action="Add a compact analysis plan or matrix that links each objective, research question or hypothesis to the data source, variables or themes, analytic technique, assumptions or diagnostics and expected result table.",
                    example="For example, a quantitative thesis can use columns for objective, variables, scale/composite, statistical test or model, assumption checks and result table; a qualitative thesis can use columns for objective, data source, coding procedure, theme evidence and trustworthiness check.",
                ))

    if ch4_text and has_analysis_terms:
        # This check does not claim a result is wrong. It forces the report to preserve enough analysis evidence for examiner verification.
        quantitative_methods = methods & {"correlation", "linear_regression", "logistic_regression", "anova", "t_test", "chi_square", "sem", "factor_analysis", "moderation", "mediation", "panel_time_series", "experimental"}
        qualitative_only = "qualitative" in methods and not quantitative_methods
        required_result_terms = ("quotation", "theme", "coding", "trustworthiness", "credibility") if qualitative_only else ("confidence interval", "effect size", "diagnostic", "assumption", "model fit", "validity", "reliability", "robust", "standard error", "degrees of freedom", "df", "p-value", "p value")
        if not _has_any(ch4_text, required_result_terms):
            target = _find_rows(rows, r"\b(?:results|findings|table|analysis|model|test|theme)\b", chapters={4})[:1]
            if target:
                row = target[0]
                example_text = (
                    "For example, a qualitative results section should show themes with enough participant or documentary evidence to justify each interpretation."
                    if qualitative_only
                    else "For example, a statistical results table should allow the reader to check the model estimates, uncertainty measures, significance decisions and relevant diagnostics required by the method used."
                )
                output.append(_make_issue(
                    finding_id="AR-REVIEW-RESULTS-EVIDENCE-VERIFIABILITY",
                    category="results_and_interpretation",
                    section=source_section(row),
                    title="The results chapter needs stronger evidence for verifying the analysis",
                    severity="major",
                    confidence=0.82,
                    evidence_ids=[paragraph_id(row)],
                    quote=clean_text(row.get("text", ""))[:300],
                    assessment="The results chapter appears to report findings, but the extracted evidence does not show enough method-appropriate verification detail.",
                    consequence="A reader may accept the stated conclusions only on trust rather than being able to verify whether the analysis supports them.",
                    action="Revise the results so every major finding is supported by the reporting elements required by the actual method used, then interpret direction, magnitude, uncertainty and practical meaning before making a decision on the objective or hypothesis.",
                    example=example_text,
                ))

    if ch4_text and (ch5_text or re.search(r"\bdiscussion\b", ch4_text, flags=re.I)):
        # Flag a discussion that reports results but lacks interpretive language.
        discussion_rows = _find_rows(rows, r"\b(?:discussion|discuss|interpret|compared with|consistent with|contrary to|theory|literature|implies|meaning)\b", chapters={4, 5})
        result_rows = _find_rows(rows, r"\b(?:result|finding|table|significant|not significant|hypothesis|theme|coefficient|mean)\b", chapters={4})
        if result_rows and not discussion_rows:
            row = result_rows[0]
            output.append(_make_issue(
                finding_id="AR-REVIEW-DISCUSSION-INTERPRETIVE-DEPTH",
                category="discussion_and_integration",
                section=source_section(row),
                title="The discussion should interpret the findings rather than only restating results",
                severity="major",
                confidence=0.83,
                evidence_ids=[paragraph_id(row)],
                quote=clean_text(row.get("text", ""))[:300],
                assessment="The results are presented, but the surrounding chapter does not clearly show a developed discussion that explains their meaning against theory, prior studies and the study context.",
                consequence="Without interpretation, the chapter reads as output reporting rather than doctoral or graduate-level knowledge construction.",
                action="For each objective or hypothesis, explain what the result means, how it compares with prior literature or theory, why the finding may have occurred in the study context, and what limitation affects the interpretation.",
                example="For example, after reporting a significant or non-significant model result, discuss whether the direction and size of the relationship support the theoretical expectation and what that means for the population or setting studied.",
            ))

    # Overclaiming safeguard for non-experimental and cross-sectional designs.
    doc = _doc_text(rows)
    if re.search(r"\b(?:cross[- ]sectional|survey|questionnaire|correlational|descriptive)\b", doc, flags=re.I) and re.search(r"\b(?:causes?|causal|impact|effect of|influence of|led to|leads to)\b", ch4_text + "\n" + ch5_text, flags=re.I):
        target = _find_rows(rows, r"\b(?:causes?|causal|impact|effect of|influence of|led to|leads to)\b", chapters={4, 5})[:1]
        if target:
            row = target[0]
            output.append(_make_issue(
                finding_id="AR-REVIEW-CLAIM-STRENGTH-DESIGN-FIT",
                category="results_and_interpretation",
                section=source_section(row),
                title="The strength of the claim should match the research design",
                severity="major",
                confidence=0.86,
                evidence_ids=[paragraph_id(row)],
                quote=clean_text(row.get("text", ""))[:300],
                assessment="The document signals a non-experimental or survey-type design but uses language that may imply causal effect or strong influence.",
                consequence="Overstating causality can make otherwise useful results appear methodologically weak, especially during examiner review.",
                action="Qualify causal or impact language unless the design, timing, control strategy and analysis support causal inference. Use wording such as predicts, is associated with, is linked to, or is a significant explanatory factor where appropriate.",
                example="For example, in a cross-sectional survey, write that a variable significantly predicts or is associated with the outcome, rather than claiming that it causes the outcome unless the design justifies that claim.",
            ))

def thorough_review_deterministic_issues(
    paragraphs: Sequence[Dict[str, Any]],
    *,
    academic_level: Any = "",
    research_approach: Any = "",
) -> List[Dict[str, Any]]:
    """Generic evidence-anchored safeguards for methods-results-discussion review.

    The layer is deliberately method-agnostic. It detects the analysis families
    signalled by the uploaded thesis or dissertation and then checks only the
    reporting, diagnostic, alignment and interpretation requirements that belong
    to those detected methods. It does not assume the example study used to test
    VProfessor, and it does not recompute results from raw data.
    """
    rows = _current(paragraphs)
    output: List[Dict[str, Any]] = []

    # Analysis route must be consistent from methods to results.
    _add_analysis_method_drift_issue(rows, output)

    # Hypothesis/objective numbering and thesis-state checks are generic.
    _add_duplicate_hypothesis_issue(rows, output)

    # ArticleReady-style report-first audit. This improves the depth of methods,
    # results and discussion feedback without tying the review to one example study.
    _add_articleready_style_generic_audit(rows, output)

    completed_signals = _find_rows(rows, r"\b(?:data\s+were\s+collected|respondents?\s+were|usable responses?|findings|results|analysed|analyzed)\b", chapters={3, 4, 5})
    future_methods = _find_rows(rows, r"\b(?:will\s+be\s+(?:collected|analysed|analyzed|used|computed|administered|obtained|selected|tested|coded)|will\s+(?:collect|analyse|analyze|administer|use|ensure|test|code))\b", chapters={3})
    if future_methods and completed_signals:
        target = future_methods[0]
        output.append(_make_issue(
            finding_id="GENERIC-METHODS-FUTURE-TENSE",
            category="methodological_rigour",
            section=source_section(target),
            title="Chapter Three retains proposal-style future tense",
            severity="moderate",
            confidence=0.94,
            evidence_ids=[paragraph_id(target), paragraph_id(completed_signals[0])],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The methodology still uses future-tense procedural wording even though the thesis reports completed data collection, analysis or results.",
            consequence="The chapter reads partly like a proposal and partly like a completed thesis, weakening methodological credibility.",
            action="Convert completed procedures to past tense and reserve future tense only for recommendations or future research.",
            example="For example, revise 'questionnaires will be administered' to 'questionnaires were administered' if the data have already been collected.",
        ))

    _add_generic_method_specific_issues(rows, output)

    # Incomplete results/discussion markers.
    undone_rows = _find_rows(rows, r"\bNOT\s+DONE\b|\bto\s+be\s+completed\b|\bpending\b|\bto\s+be\s+inserted\b|\badd\s+(?:discussion|results|analysis)\b", chapters={4, 5})
    if undone_rows:
        target = undone_rows[0]
        output.append(_make_issue(
            finding_id="GENERIC-INCOMPLETE-RESULTS-DISCUSSION-MARKER",
            category="discussion_and_integration",
            section=source_section(target),
            title="An unfinished results or discussion marker remains in the thesis",
            severity="critical",
            confidence=0.98,
            evidence_ids=[paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="The thesis contains a visible marker showing that a results or discussion subsection is not completed.",
            consequence="This makes the submission appear unfinished and will seriously weaken examiner confidence in the work.",
            action="Complete the subsection by linking the relevant result to the objective or hypothesis, the chosen method, prior literature, theory, context and the limits of the design.",
            example="For example, after a statistical result, explain the direction and magnitude of the finding, whether the hypothesis is supported, how it compares with prior studies and what it means in the study context.",
        ))

    # Descriptive interpretation scale inconsistency.
    high_mean_rows = _find_rows(rows, r"\b(?:M|Mean)\s*=\s*(3\.\d+|2\.\d+)\b.*\bhigh\b|\bhigh\b.*\b(?:M|Mean)\s*=\s*(3\.\d+|2\.\d+)\b", chapters={4})
    if high_mean_rows:
        target = high_mean_rows[0]
        output.append(_make_issue(
            finding_id="GENERIC-DESCRIPTIVE-MEAN-INTERPRETATION",
            category="results_and_interpretation",
            section=source_section(target),
            title="A descriptive mean interpretation may not match the stated scale category",
            severity="moderate",
            confidence=0.78,
            evidence_ids=[paragraph_id(target)],
            quote=clean_text(target.get("text", ""))[:260],
            assessment="A mean in the moderate range appears to be interpreted as high without a clearly stated cut-off scheme in the same results discussion.",
            consequence="The prevalence, level or extent of the construct may be overstated, especially where the result answers a descriptive research question.",
            action="State the interpretation scale, compute the composite mean from respondent-level scores where applicable, and ensure the category assigned to each mean follows the stated thresholds.",
            example="For example, if a five-point scale classifies 3.40–4.19 as high, state that rule before applying it; if the rule classifies 2.61–3.40 as moderate, revise the interpretation accordingly.",
        ))

    _add_r2_f_inconsistency(rows, output)
    _table_number_issues(rows, output)

    # Deduplicate by finding and evidence paragraph to avoid repetitive output.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in output:
        key = (item.get("finding_id"), tuple(item.get("evidence_paragraph_ids") or []))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
