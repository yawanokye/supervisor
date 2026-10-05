"""A reusable author-year index. Matching is separate from claim support."""
from __future__ import annotations
import re
from typing import Any, Mapping, Sequence

def build_reference_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries = []
    for row in rows:
        if not row.get('is_reference_entry'):
            continue
        text = str(row.get('text') or '')
        year = re.search(r'\b(?:19|20)\d{2}[a-z]?\b', text)
        author = re.match(r'\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ’\'-]+)', text)
        if year and author:
            entries.append({'key': author.group(1).lower()+'|'+year.group(0).lower(), 'text': text,
                'paragraph': row.get('paragraph'), 'claim_support': 'unverified, requires source text'})
    return {'entries': entries, 'keys': sorted({e['key'] for e in entries}), 'source_existence': 'not independently verified', 'claim_support': 'not implied by author-year matching'}

def compact_alignment_context(rows: Sequence[dict], per_chapter_chars: int = 10000) -> list[dict]:
    # Preserve research logic and relevant tables before ordinary summaries.
    terms = r'objective|question|hypothes|framework|theor|sample|population|measurement|design|model|regression|results|conclusion'
    chosen = []; used = {}
    for row in sorted(rows, key=lambda r: (0 if re.search(terms, str(r.get('heading') or ''), re.I) else 1, int(r.get('paragraph') or 0))):
        if row.get('is_reference_entry'): continue
        if not re.search(terms, str(row.get('heading') or '')+' '+str(row.get('text') or ''), re.I): continue
        chapter = row.get('chapter_number')
        size = len(str(row.get('text') or ''))
        if used.get(chapter,0)+size > per_chapter_chars: continue
        used[chapter] = used.get(chapter,0)+size
        chosen.append(row)
    return sorted(chosen, key=lambda r: int(r.get('paragraph') or 0))
