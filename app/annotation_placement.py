"""Verify a finding against the actual export source before placing any comment."""
from __future__ import annotations

from .document_parser import clean_text, docx_visible_text, normalised


def locator_text(locator: dict) -> str:
    if locator.get('text'):
        return clean_text(locator['text'])
    if locator.get('paragraph') is not None:
        return clean_text(docx_visible_text(locator['paragraph']))
    return ' | '.join(clean_text(docx_visible_text(p)) for p in locator.get('cell_paragraphs',[]))


def resolve_verified_location(row: dict, source_map: dict) -> int:
    quote = clean_text(row.get('exact_source_text') or row.get('problematic_quote'))
    evidence = [e for e in row.get('evidence',[]) if e.get('document_role','current') == 'current']
    # The quoted passage is the primary location, other evidence may corroborate it.
    evidence.sort(key=lambda e:0 if quote and quote.casefold() in clean_text(e.get('text')).casefold() else 1)
    for item in evidence:
        expected = clean_text(item.get('text'))
        chapter = item.get('chapter_number') if item.get('chapter_number') is not None else row.get('chapter_number')
        table_number = clean_text(item.get('table_number'))
        section = normalised(item.get('section_reference') or item.get('heading') or '')
        def section_key(value):
            import re
            return re.sub(r'^\d+(?:\.\d+)*\s+', '', normalised(value))
        table_kind = item.get('source_kind') == 'table_row' or item.get('table_row') is not None
        def matches(locator):
            text = locator_text(locator)
            if not text: return False
            if chapter is not None and locator.get('chapter_number') is not None and int(chapter) != int(locator['chapter_number']): return False
            if section and locator.get('heading') and section_key(section) != section_key(locator['heading']): return False
            if table_kind and locator.get('kind') != 'table_row': return False
            if table_number and clean_text(locator.get('table_number')) != table_number: return False
            # Full row/paragraph evidence must agree. A quote alone is sufficient only if unique.
            if expected and clean_text(expected).casefold() not in text.casefold(): return False
            if quote and quote.casefold() not in text.casefold(): return False
            return bool(expected or quote)
        candidates = [n for n,locator in source_map.items() if matches(locator)]
        if len(candidates) != 1:
            continue
        number = candidates[0]
        text = locator_text(source_map[number])
        if quote and text.casefold().count(quote.casefold()) > 1:
            # Repeated words within one paragraph cannot identify the intended sentence.
            continue
        return number
    return 0


def validate_review_placements(rows: list[dict], review: dict, source_map: dict, missing_section_predicate) -> list[dict]:
    verified = []; unresolved = []
    for row in rows:
        if row.get('status') not in {'partly_meets_requirement','does_not_meet_requirement','manual_review_required'} or row.get('annotation_eligible') is False or missing_section_predicate(row): continue
        number = resolve_verified_location(row,source_map)
        if number:
            row['_verified_paragraph_number'] = number
            row['placement_status'] = 'verified_source_location'
            locator = source_map[number]
            original = next((e for e in row.get('evidence',[]) if e.get('document_role','current') == 'current'),{})
            primary = {**original,'paragraph':number,'text':locator_text(locator),'document_role':'current',
                'heading':locator.get('heading'), 'section_reference':locator.get('heading'),
                'chapter_number':locator.get('chapter_number'), 'table_index':locator.get('table_index'),
                'table_row':locator.get('table_row'), 'table_number':locator.get('table_number')}
            row['evidence'] = [primary,*[e for e in row.get('evidence',[]) if e is not original]]
            verified.append(row.get('finding_number'))
        else:
            row['annotation_eligible'] = False
            row['placement_status'] = 'manual_location_required'
            row['placement_note'] = 'Retained in the report. No unique source location was verified, so no margin comment was attached.'
            unresolved.append(row.get('finding_number'))
        for original in [*review.get('canonical_findings',[]),*review.get('academic_findings',[])]:
            same_id = row.get('finding_id') and row.get('finding_id') == original.get('finding_id')
            same_number = row.get('finding_number') and row.get('finding_number') == original.get('finding_number')
            if same_id or same_number:
                for key in ('annotation_eligible','placement_status','placement_note','_verified_paragraph_number','evidence'):
                    if key in row: original[key] = row[key]
    prior = review.get('annotation_placement_audit') or {}
    unresolved = sorted(n for n in set(unresolved) | set(prior.get('manual_location_finding_numbers') or []) if n)
    review['annotation_placement_audit'] = {'verified_finding_numbers':sorted(n for n in verified if n),
        'manual_location_finding_numbers':unresolved,'manual_location_count':len(unresolved),
        'arbitrary_body_fallback_allowed':False}
    review.setdefault('summary',{})['manual_comment_location_count'] = len(unresolved)
    return rows
