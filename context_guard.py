from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .document_parser import clean_text, normalised


COUNTRY_ALIASES: Dict[str, str] = {
    "ghana": "Ghana",
    "south africa": "South Africa",
    "kenya": "Kenya",
    "nigeria": "Nigeria",
    "uganda": "Uganda",
    "tanzania": "Tanzania",
    "rwanda": "Rwanda",
    "ethiopia": "Ethiopia",
    "zambia": "Zambia",
    "zimbabwe": "Zimbabwe",
    "botswana": "Botswana",
    "namibia": "Namibia",
    "malawi": "Malawi",
    "mozambique": "Mozambique",
    "sierra leone": "Sierra Leone",
    "liberia": "Liberia",
    "gambia": "The Gambia",
    "the gambia": "The Gambia",
    "senegal": "Senegal",
    "cote d ivoire": "Côte d’Ivoire",
    "ivory coast": "Côte d’Ivoire",
    "burkina faso": "Burkina Faso",
    "togo": "Togo",
    "benin": "Benin",
    "cameroon": "Cameroon",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "u k": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "u s a": "United States",
    "canada": "Canada",
    "australia": "Australia",
    "new zealand": "New Zealand",
    "china": "China",
    "india": "India",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "sri lanka": "Sri Lanka",
    "malaysia": "Malaysia",
    "singapore": "Singapore",
    "indonesia": "Indonesia",
    "philippines": "Philippines",
    "japan": "Japan",
    "south korea": "South Korea",
    "germany": "Germany",
    "france": "France",
    "italy": "Italy",
    "spain": "Spain",
    "netherlands": "Netherlands",
    "belgium": "Belgium",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "finland": "Finland",
    "switzerland": "Switzerland",
    "ireland": "Ireland",
    "brazil": "Brazil",
    "mexico": "Mexico",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "peru": "Peru",
    "jamaica": "Jamaica",
    "egypt": "Egypt",
    "morocco": "Morocco",
    "saudi arabia": "Saudi Arabia",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
}

KNOWN_EXTERNAL_PLACES: Dict[str, str] = {
    "gauteng": "South Africa",
    "johannesburg": "South Africa",
    "cape town": "South Africa",
    "nairobi": "Kenya",
    "mombasa": "Kenya",
    "lagos": "Nigeria",
    "abuja": "Nigeria",
    "london": "United Kingdom",
    "manchester": "United Kingdom",
    "birmingham": "United Kingdom",
    "new york": "United States",
    "california": "United States",
    "texas": "United States",
    "toronto": "Canada",
    "ontario": "Canada",
    "sydney": "Australia",
    "melbourne": "Australia",
}

SECTOR_TERMS = (
    "mining", "construction", "education", "health", "healthcare", "banking",
    "finance", "procurement", "agriculture", "tourism", "manufacturing",
    "public sector", "private sector", "telecommunication", "energy",
    "community development", "corporate social responsibility", "csr",
    "mobile phone retail", "mobile phone", "retail", "supply chain",
)

CITATION_PATTERNS = [
    re.compile(r"\b[A-Z][A-Za-z'’-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’-]+|\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\)"),
    re.compile(r"\([A-Z][A-Za-z'’-]+(?:\s+et\s+al\.)?(?:,|\s+and\s+[A-Z][A-Za-z'’-]+,?)\s*(?:19|20)\d{2}[a-z]?\)"),
]


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", text, flags=re.I))


def _unique(values: Iterable[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        text = clean_text(value)
        key = normalised(text)
        if text and key and key not in seen:
            seen.add(key)
            output.append(text)
    return output


FRONT_MATTER_LABELS = {
    "university of cape coast", "college of humanities and legal studies",
    "department of marketing and supply chain management", "school of business",
    "by", "declaration", "certification", "dedication", "acknowledgement",
    "abstract", "list of tables", "list of figures", "keywords",
}

STUDY_CONTEXT_HEADINGS = {
    "abstract", "background to the study", "problem statement", "statement of the problem",
    "purpose of the study", "research objectives", "research questions", "delimitation",
    "scope of the study", "study area", "study setting", "study population", "population",
    "sampling procedures and sample size", "sampling procedure and sample size",
}


def _title_or_opening_focus(paragraphs: Sequence[Dict[str, Any]]) -> str:
    candidates: List[Tuple[int, int, str]] = []
    for index, paragraph in enumerate(paragraphs[:45]):
        text = clean_text(paragraph.get("text", ""))
        low = normalised(text)
        if not text or low in FRONT_MATTER_LABELS or low.startswith("chapter "):
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", text) or re.fullmatch(r"[A-Z .'-]+\([^)]*\)", text):
            continue
        words = text.split()
        if len(words) < 5 or len(words) > 35:
            continue
        score = 0
        if paragraph.get("is_heading"):
            score += 4
        if ":" in text:
            score += 2
        if any(term in low for term in ("effect", "impact", "relationship", "adoption", "evidence", "study")):
            score += 3
        if any(term in low for term in ("submitted", "fulfilment", "requirement", "award of")):
            score -= 8
        candidates.append((score, -index, text))
    if candidates:
        return max(candidates)[2]
    for paragraph in paragraphs:
        text = clean_text(paragraph.get("text", ""))
        if text:
            return text
    return ""


def _study_context_rows(paragraphs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    title = _title_or_opening_focus(paragraphs)
    title_key = normalised(title)
    for paragraph in paragraphs:
        text = clean_text(paragraph.get("text", ""))
        heading = normalised(clean_text(paragraph.get("heading", "")))
        if not text or paragraph.get("is_toc_entry"):
            continue
        if normalised(text) == title_key:
            selected.append(paragraph)
            continue
        if heading in STUDY_CONTEXT_HEADINGS:
            selected.append(paragraph)
    return selected


def _context_paragraphs(paragraphs: Sequence[Dict[str, Any]], limit: int = 18) -> List[str]:
    selected: List[str] = []
    for paragraph in _study_context_rows(paragraphs):
        text = clean_text(paragraph.get("text", ""))
        if text and normalised(text) not in {"top of form", "bottom of form"}:
            selected.append(text[:900])
        if len(selected) >= limit:
            break
    return _unique(selected)



def _detected_sectors(context_low: str) -> List[str]:
    found = [term for term in SECTOR_TERMS if _contains_phrase(context_low, term)]
    # Prefer the most specific study field. Broad public/private-sector mentions
    # often describe prior policy literature rather than the sampled industry.
    if "mobile phone retail" in found:
        preferred = ["mobile phone retail"]
        if "procurement" in found:
            preferred.append("procurement")
        if "supply chain" in found:
            preferred.append("supply chain")
        return preferred
    return _unique(found)

def build_context_lock(
    paragraphs: Sequence[Dict[str, Any]],
    summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = summary or {}
    source_text = "\n".join(clean_text(item.get("text", "")) for item in paragraphs if clean_text(item.get("text", "")))
    source_low = normalised(source_text)
    context_rows = _study_context_rows(paragraphs)
    context_text = "\n".join(clean_text(item.get("text", "")) for item in context_rows if clean_text(item.get("text", "")))
    context_low = normalised(context_text)

    countries = []
    for alias, canonical in COUNTRY_ALIASES.items():
        if _contains_phrase(context_low, alias):
            countries.append(canonical)

    location_phrases = re.findall(
        r"\b(?:[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3})\s+"
        r"(?:Region|District|Municipality|Metropolis|Province|State|County|City|Town)\b",
        context_text,
    )
    organisation_phrases = re.findall(
        r"\b(?:[A-Z][A-Za-z'’&.-]+(?:\s+[A-Z][A-Za-z'’&.-]+){0,5})\s+"
        r"(?:University|Institute|College|Hospital|Ministry|Agency|Authority|Company|Corporation|Bank)\b",
        context_text,
    )
    sectors = _detected_sectors(context_low)

    title = _title_or_opening_focus(paragraphs)

    return {
        "title_or_opening_focus": title[:500],
        "confirmed_countries": _unique(countries),
        "confirmed_locations": _unique(location_phrases),
        "confirmed_organisations": _unique(organisation_phrases),
        "confirmed_sectors": _unique(sectors),
        "declared_academic_level": clean_text(summary.get("academic_level", "")),
        "declared_research_approach": clean_text(summary.get("research_approach", "")),
        "review_stage": clean_text(summary.get("submission_stage", "")),
        "context_excerpt": _context_paragraphs(paragraphs),
        "source_text_normalised": source_low,
        "strict_rule": (
            "Use only the countries, locations, organisations, populations and sectors explicitly present in the source. "
            "If a detail is unknown, omit the illustrative example and instruct the student to provide or verify the missing detail without inserting a placeholder token."
        ),
    }


def public_context(context_lock: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: context_lock.get(key)
        for key in (
            "title_or_opening_focus", "confirmed_countries", "confirmed_locations",
            "confirmed_organisations", "confirmed_sectors", "declared_academic_level",
            "declared_research_approach", "review_stage",
        )
    }


def _replace_disallowed_geography(text: str, context_lock: Dict[str, Any]) -> Tuple[str, bool]:
    if not text:
        return text, False
    source_low = str(context_lock.get("source_text_normalised") or "")
    adjusted = False
    output = text

    for alias, canonical in sorted(COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if not _contains_phrase(output, alias):
            continue
        if _contains_phrase(source_low, alias) or _contains_phrase(source_low, canonical.lower()):
            continue
        output = re.sub(
            rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])",
            "[study country]",
            output,
            flags=re.I,
        )
        adjusted = True

    for place, country in sorted(KNOWN_EXTERNAL_PLACES.items(), key=lambda item: len(item[0]), reverse=True):
        if not _contains_phrase(output, place):
            continue
        if _contains_phrase(source_low, place):
            continue
        output = re.sub(
            rf"(?<![A-Za-z]){re.escape(place)}(?![A-Za-z])",
            "the confirmed study setting",
            output,
            flags=re.I,
        )
        adjusted = True

    return output, adjusted


def _replace_unverified_citations(text: str, context_lock: Dict[str, Any]) -> Tuple[str, bool]:
    if not text:
        return text, False
    source_low = str(context_lock.get("source_text_normalised") or "")
    output = text
    adjusted = False
    for pattern in CITATION_PATTERNS:
        matches = list(pattern.finditer(output))
        for match in reversed(matches):
            citation = clean_text(match.group(0))
            if normalised(citation) and normalised(citation) in source_low:
                continue
            output = output[:match.start()] + "a verified scholarly source" + output[match.end():]
            adjusted = True
    return output, adjusted


def _replace_unverified_statistics(text: str, context_lock: Dict[str, Any]) -> Tuple[str, bool]:
    if not text:
        return text, False
    source_low = str(context_lock.get("source_text_normalised") or "")
    output = text
    adjusted = False
    for match in reversed(list(re.finditer(r"\b\d+(?:\.\d+)?\s*%", output))):
        value = clean_text(match.group(0))
        if normalised(value) in source_low:
            continue
        output = output[:match.start()] + "a verified statistic" + output[match.end():]
        adjusted = True
    return output, adjusted


def sanitise_generated_text(value: Any, context_lock: Dict[str, Any]) -> Tuple[str, bool]:
    text = clean_text(value)
    text, geo = _replace_disallowed_geography(text, context_lock)
    text, citations = _replace_unverified_citations(text, context_lock)
    text, stats = _replace_unverified_statistics(text, context_lock)
    text = re.sub(r"\bExample:\s*Example:\s*", "Example: ", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text, bool(geo or citations or stats)


def sanitise_issue(issue: Dict[str, Any], context_lock: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(issue)
    adjusted = False
    for field in (
        "section", "issue_title", "assessment", "academic_consequence",
        "required_action", "illustrative_guidance",
    ):
        original = clean_text(output.get(field, ""))
        cleaned, changed = sanitise_generated_text(original, context_lock)
        if field == "illustrative_guidance" and changed:
            # Do not export invented examples or visible placeholder prompts.
            # The required action already tells the student what must be verified.
            cleaned = ""
        output[field] = cleaned
        adjusted = adjusted or changed

    category = str(output.get("category") or "")
    verification_terms = normalised(
        " ".join(
            str(output.get(field) or "")
            for field in ("issue_title", "assessment", "required_action")
        )
    )
    output["source_verification_required"] = bool(
        output.get("source_verification_required")
        or category in {"citations_and_sources", "ethics_and_integrity"}
        or any(term in verification_terms for term in (
            "verify source", "requires verification", "original source", "citation", "reference list",
            "unsupported statistic", "unverified", "check the source",
        ))
    )
    output["guidance_type"] = output.get("guidance_type") or (
        "source_verification" if output["source_verification_required"]
        else "conditional_guidance" if any(term in normalised(output.get("required_action", "")) for term in ("if the", "where the", "depending on"))
        else "direct_correction"
    )
    output["context_guard_adjusted"] = bool(output.get("context_guard_adjusted") or adjusted)
    return output
