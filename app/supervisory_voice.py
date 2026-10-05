"""Varied supervisory prose with unchanged evidence and corrective obligations."""
from __future__ import annotations
import re
import hashlib
import json
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Mapping

VOICE_CONTRACT = '''Write margin comments as an experienced human supervisor responding to this particular passage. Vary openings and sentence rhythm according to the problem, not by mechanically adding synonyms. Use diagnosis-first comments for contradictions, action-first comments for clear reporting repairs, and a focused question followed by a concrete instruction when genuine clarification is required. Do not ask questions instead of identifying a confirmed error. Explain an academic consequence when it helps the student understand the change. Most comments need 30-70 words, but a simple correction may be shorter and a complex methodological issue may need up to 100. Never pad a comment to meet a word count. Avoid repeating “This section”, “The study”, “You need to”, “Rewrite the cited passage”, fixed labels or identical three-part sentences. Use plain British English, no em dashes and no invented citations, results or examples. Refer to the actual construct, claim, coefficient, objective, method or passage. State the precise change and where a recurring correction should apply. Acknowledge an actual strength only when supported and useful. Severity and certainty must match the evidence. The supervisory_comment must express the same verified diagnosis and required_action as the structured fields, with no new scholarly claims. Do not fill a comment quota or manufacture faults in adequate work.'''

def _tokens(text: Any) -> set[str]:
    return {w for w in re.findall(r'[a-z]{4,}',str(text).lower()) if w not in {'this','that','with','from','have','should','their','study','section','revise','report'}}

def narrative_basis(row: Mapping[str,Any]) -> str:
    values = [row.get('item') or row.get('issue_title'), row.get('assessment') or row.get('comment'),
        row.get('academic_consequence'), row.get('required_action'), row.get('problematic_quote')]
    return hashlib.sha256(json.dumps([str(value or '').strip() for value in values]).encode()).hexdigest()

def usable_narrative(row: Mapping[str,Any]) -> str:
    text = str(row.get('supervisory_comment') or '').strip().replace('—', ', ')
    if not text or len(text.split()) > 110: return ''
    if row.get('_supervisory_comment_basis') and row['_supervisory_comment_basis'] != narrative_basis(row): return ''
    if re.search(r'\b(?:problem|consequence|required action|academic implication)\s*:',text,re.I): return ''
    if re.search(r'rewrite the cited passage|insert (?:the )?missing information|\[.*?\]',text,re.I): return ''
    action = _tokens(row.get('required_action'))
    if action and len(action & _tokens(text)) < min(2,len(action)): return ''
    # Keep each separate obligation, including a second sentence for a recurring correction.
    for sentence in re.split(r'[.!?](?:\s+|$)',str(row.get('required_action') or '')):
        obligation = _tokens(sentence)
        if obligation and len(obligation & _tokens(text)) < min(2,len(obligation)): return '' 
    supported = ' '.join(str(row.get(k) or '') for k in ('assessment','comment','item','issue_title','required_action','academic_consequence','problematic_quote','exact_source_text'))
    if not _tokens(text) & _tokens(supported): return ''
    numbers = set(re.findall(r'(?<![a-z])\d+(?:\.\d+)?',text.lower()))
    if not numbers.issubset(set(re.findall(r'(?<![a-z])\d+(?:\.\d+)?',supported.lower()))): return ''
    return text

def comment_variation_audit(rows: list[dict]) -> dict:
    from .natural_supervisor_comment import natural_supervisor_comment
    texts = [natural_supervisor_comment(r) for r in rows]
    openings = Counter(' '.join(re.findall(r'\w+',t.lower())[:4]) for t in texts if t)
    repeated = {k:v for k,v in openings.items() if v > max(2,len(texts)//5)}
    duplicates = []
    for i,text in enumerate(texts):
        for j,earlier in enumerate(texts[:i]):
            if text and SequenceMatcher(None,text.lower(),earlier.lower()).ratio() >= .92:
                duplicates.append([j+1,i+1])
    return {'comment_count':len(texts), 'repeated_openings':repeated, 'near_duplicate_comment_pairs':duplicates,
        'generic_rewrite_count':sum('rewrite the cited passage' in t.lower() for t in texts),
        'word_counts':[len(t.split()) for t in texts], 'note':'Variation is checked without changing evidence, severity or the required correction.'}
