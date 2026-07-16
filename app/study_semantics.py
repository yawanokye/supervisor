from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Set

from .document_parser import clean_text, normalised

# Domain-neutral vocabulary used to distinguish substantive study terms from
# research boilerplate, settings and generic population labels.
ACADEMIC_STOPWORDS: Set[str] = {
    "the", "this", "that", "these", "those", "study", "research", "purpose",
    "aim", "objective", "objectives", "question", "questions", "hypothesis",
    "hypotheses", "chapter", "work", "to", "examine", "assess", "determine",
    "investigate", "explore", "analyse", "analyze", "evaluate", "identify",
    "establish", "describe", "compare", "test", "estimate", "measure", "current",
    "adopted", "proposed", "level", "extent", "relationship", "effect", "impact",
    "influence", "role", "association", "among", "within", "between", "regarding",
    "practice", "practices", "and", "or", "of", "on", "in", "at", "by", "for",
    "with", "from", "as", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "how", "what", "which", "whether", "towards", "through", "using",
    "case", "context", "setting", "sector", "country", "countries", "region",
    "district", "municipality", "community", "communities", "institution",
    "institutions", "organisation", "organisations", "organization", "organizations",
    "company", "companies", "firm", "firms", "enterprise", "enterprises", "bank",
    "banks", "school", "schools", "college", "colleges", "university", "universities",
    "hospital", "hospitals", "participant", "participants", "respondent", "respondents",
    "student", "students", "teacher", "teachers", "employee", "employees", "staff",
    "manager", "managers", "household", "households", "patient", "patients", "people",
    "population", "sample", "unit", "units", "analysis", "data", "evidence",
}

POPULATION_HEADS = (
    "participants", "respondents", "students", "teachers", "lecturers", "employees",
    "staff", "managers", "customers", "patients", "households", "farmers", "workers",
    "firms", "enterprises", "companies", "organisations", "organizations", "banks",
    "schools", "colleges", "universities", "hospitals", "institutions", "countries",
    "regions", "districts", "communities", "cases", "records", "transactions",
)

EMPIRICAL_UNIT_PATTERN = re.compile(
    r"\b(?:\d{2,}(?:,\d{3})*|\d+(?:\.\d+)?\s*%)\b"
    r"(?:\s+[A-Za-z][A-Za-z'’\-]*){0,6}\s+"
    r"(?:people|persons?|participants?|respondents?|students?|teachers?|lecturers?|"
    r"employees?|staff|managers?|customers?|patients?|households?|farmers?|workers?|"
    r"firms?|enterprises?|companies|organisations?|organizations?|banks?|schools?|"
    r"colleges?|universities|hospitals?|institutions?|countries|regions|districts|"
    r"communities|cases|observations?|records?|transactions?|projects?|facilities|"
    r"hectares?|tonnes?|deaths?|events?)\b",
    flags=re.I,
)

CITATION_PATTERN = re.compile(
    r"\([^)]*(?:19|20)\d{2}[a-z]?[^)]*\)|\b[A-Z][A-Za-z'’\-]+\s*\((?:19|20)\d{2}[a-z]?\)",
    flags=re.I,
)


def content_tokens(text: str, *, extra_stopwords: Iterable[str] = ()) -> Set[str]:
    stop = ACADEMIC_STOPWORDS | {normalised(value) for value in extra_stopwords if value}
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9'’\-]{2,}", normalised(text))
        if token not in stop and not token.isdigit()
    }


def objective_focus_phrases(text: str) -> List[str]:
    """Extract substantive noun phrases from objectives without assuming a domain."""
    value = clean_text(text)
    if not value:
        return []
    clauses = [clean_text(part) for part in re.split(r"[.;\n]+|(?=\bTo\s+(?:assess|examine|determine|investigate|explore|evaluate|identify|establish|compare|estimate|test|analyse|analyze)\b)", value, flags=re.I) if clean_text(part)]
    candidates: List[str] = []
    patterns = (
        r"(?:effect|impact|influence)\s+of\s+(.+?)\s+on\s+(.+?)(?:\s+(?:among|within|in|at|for)\s+|$)",
        r"relationship\s+between\s+(.+?)\s+and\s+(.+?)(?:\s+(?:among|within|in|at|for)\s+|$)",
        r"(?:role|contribution)\s+of\s+(.+?)\s+(?:in|on|towards)\s+(.+?)(?:\s+(?:among|within|in|at|for)\s+|$)",
        r"(?:level|extent|rate|status|prevalence|incidence|effectiveness)\s+of\s+(.+?)(?:\s+(?:among|within|in|at|for)\s+|$)",
    )
    for clause in clauses:
        found = False
        for pattern in patterns:
            match = re.search(pattern, clause, flags=re.I)
            if not match:
                continue
            found = True
            candidates.extend(clean_text(group).strip(" ,:;.-") for group in match.groups())
        if found:
            continue
        cleaned = re.sub(
            r"^(?:\(?[ivxlcdm0-9]+[.)]?\s*)?to\s+(?:assess|examine|determine|investigate|explore|evaluate|identify|establish|compare|estimate|test|analyse|analyze|describe)\s+",
            "",
            clause,
            flags=re.I,
        )
        cleaned = re.split(r"\s+(?:among|within|in|at)\s+", cleaned, maxsplit=1, flags=re.I)[0]
        cleaned = clean_text(cleaned).strip(" ,:;.-")
        if cleaned:
            candidates.append(cleaned)

    output: List[str] = []
    seen = set()
    for phrase in candidates:
        phrase = re.sub(r"^(?:the|a|an)\s+", "", clean_text(phrase), flags=re.I)
        phrase = re.sub(r"\b(?:of|and|or|in|on|at|for|with)$", "", phrase, flags=re.I).strip(" ,:;.-")
        tokens = content_tokens(phrase)
        if not tokens:
            continue
        key = normalised(phrase)
        if key in seen:
            continue
        seen.add(key)
        output.append(phrase)
    return output[:12]


def omitted_objective_focuses(purpose_text: str, objectives_text: str) -> List[str]:
    """Return objective focuses not materially represented in the purpose."""
    purpose_low = normalised(purpose_text)
    purpose_terms = content_tokens(purpose_text)
    missing: List[str] = []
    for phrase in objective_focus_phrases(objectives_text):
        key = normalised(phrase)
        tokens = content_tokens(phrase)
        if not tokens:
            continue
        # Full phrase or most of its substantive tokens in the purpose means it
        # is already represented. This is deliberately conservative.
        covered = key in purpose_low or len(tokens & purpose_terms) >= max(1, len(tokens) - 1)
        if covered:
            continue
        if len(tokens - purpose_terms) < 1:
            continue
        missing.append(phrase)
    # Prefer distinct, concise focuses and suppress phrases nested in a longer one.
    output: List[str] = []
    for phrase in sorted(missing, key=lambda value: (len(value.split()), len(value))):
        key = normalised(phrase)
        if any(key in normalised(existing) or normalised(existing) in key for existing in output):
            continue
        output.append(phrase)
    return output[:6]


def extract_population_labels(text: str) -> List[str]:
    """Recover population labels explicitly used in a study description.

    The extraction is intentionally syntactic. It does not contain topic- or
    institution-specific names, and it splits coordinated labels such as
    "public universities and private universities" into separate populations.
    """
    value = clean_text(text)
    heads = "|".join(re.escape(head) for head in POPULATION_HEADS)
    label_core = rf"[A-Za-z][A-Za-z'’\-]*(?:\s+[A-Za-z][A-Za-z'’\-]*){{0,4}}\s+(?:{heads})"
    candidates: List[str] = []

    # Explicit population introductions.
    for match in re.finditer(
        rf"\b(?:among|involving|covers?|comprises?|population(?:\s+of|\s+comprises?|\s+consists?\s+of)?|sample(?:\s+of)?)\s+(?:the\s+)?({label_core})\b",
        value,
        flags=re.I,
    ):
        candidates.append(match.group(1))

    # Coordinated labels anywhere in the prose.
    for match in re.finditer(
        rf"\b({label_core})\s+and\s+({label_core})\b",
        value,
        flags=re.I,
    ):
        candidates.extend(match.groups())

    # A population label beginning a sentence, for example "Public institutions ...".
    for match in re.finditer(
        rf"(?:^|(?<=[.!?])\s+)({label_core})\b",
        value,
        flags=re.I,
    ):
        candidates.append(match.group(1))

    output: List[str] = []
    seen = set()
    for raw in candidates:
        label = clean_text(raw).strip(" ,:;.-")
        if " and " in normalised(label):
            # Coordinated populations are already captured by the dedicated
            # pattern above. Skip a broader sentence-start capture.
            continue
        label = re.sub(r"^(?:all|selected|sampled|the)\s+", "", label, flags=re.I)
        # Trim accidental lead-in material before a population marker.
        label = re.sub(r"^.*?\b(?:among|involving)\s+", "", label, flags=re.I)
        words = label.split()
        lead_stop = {"the", "a", "an", "study", "research", "chapter", "work", "discusses", "examines", "includes", "covers", "considers", "compares", "uses"}
        while len(words) > 2 and normalised(words[0]) in lead_stop:
            words.pop(0)
        label = " ".join(words)
        if not 1 <= len(label.split()) <= 6:
            continue
        key = normalised(label)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(label)
    return output[:8]


def has_traceable_context_evidence(text: str) -> bool:
    low = normalised(text)
    evidence_terms = (
        "statistics", "statistical", "data show", "survey", "report", "reported",
        "policy", "regulation", "regulatory", "administrative records", "institutional records",
        "industry data", "sector data", "official data", "census", "audit", "monitoring",
        "prevalence", "incidence", "percentage", "proportion", "rate", "trend",
    )
    return bool(CITATION_PATTERN.search(text)) and (
        any(term in low for term in evidence_terms)
        or bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|million|billion|cases|people|firms|participants|countries|years?)\b", text, flags=re.I))
    )


def contains_uncited_empirical_count(sentence: str) -> bool:
    value = clean_text(sentence)
    return bool(EMPIRICAL_UNIT_PATTERN.search(value)) and not bool(CITATION_PATTERN.search(value))


def sentence_has_citation(sentence: str) -> bool:
    return bool(CITATION_PATTERN.search(clean_text(sentence)))
