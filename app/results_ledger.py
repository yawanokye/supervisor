"""Persistent result evidence and bounded whole-thesis adjudication."""
from __future__ import annotations
import hashlib
import json
import os
import re
from collections import defaultdict
from typing import Any, Sequence

from .document_parser import clean_text, normalised
from .statistical_profile import study_statistical_profile
from .statistical_review import _header_map, _column_index, _cells, _table_groups, _number_in_cell, _evidence

def build_results_ledger(rows: Sequence[dict]) -> dict[str, Any]:
    objectives = []
    claims = []
    estimates = []
    for row in rows:
        text = clean_text(row.get('text'))
        heading = str(row.get('heading') or '')
        if row.get('is_toc_entry') or row.get('document_zone') in {'table_of_contents','list_of_tables','list_of_figures','references'}: continue
        if not row.get('is_heading') and re.search(r'objective|research question|hypothes',heading,re.I):
            objectives.append({'text':text,'kind': 'hypothesis' if re.search('hypothes',heading,re.I) else 'question' if re.search('question',heading,re.I) else 'objective','source':_evidence(row)})
        if re.search(r'\b(?:table\s+\d|p\s*[<=>]|significan\w*|coefficient|conclud\w*|recommend\w*)\b',text,re.I):
            claims.append({'text':text,'source':_evidence(row),'table_references':re.findall(r'\bTable\s+(\d+(?:\.\d+)?)',text,re.I)})
    for index, table in _table_groups(rows).items():
        headers, header = _header_map(table)
        columns = {name:_column_index(headers,*aliases) for name,aliases in {
            'coefficient':('b','beta','estimate','coefficient','r'), 'standard_error':('se','standard error','se b'),
            'statistic':('t','z','wald'), 'p_value':('p','p value','sig'), 'mean':('mean','m'), 'sample_size':('n','sample size')}.items()}
        for row in table:
            if row is header: continue
            cells = _cells(row)
            if not cells: continue
            values = {name:{'reported':cells[col],'value':_number_in_cell(cells[col])} for name,col in columns.items() if col is not None and col < len(cells)}
            if not values: continue
            estimates.append({'result_id':hashlib.sha256((str(index)+'|'+str(row.get('table_row'))+'|'+row.get('text','')).encode()).hexdigest()[:20],
                'variable':cells[0], 'table_number':row.get('table_number'), 'table_title':row.get('table_title'), 'values':values,
                'source':_evidence(row), 'verification':'extracted evidence, interpret using model profile'})
    return {'objectives_questions_hypotheses':objectives,'estimates':estimates,'narrative_claims':claims,
        'study_profile':study_statistical_profile(rows), 'raw_data_reproduced':False,
        'evidence_hash':hashlib.sha256(json.dumps([(r.get('paragraph'),r.get('text')) for r in rows],ensure_ascii=False).encode()).hexdigest(),
        'note':'Extraction is distinct from substantive alignment and independent statistical reproduction.'}

def final_audit_evidence(rows: Sequence[dict], limit: int = 60000) -> tuple[list[dict], dict]:
    groups = defaultdict(list)
    for row in rows:
        if row.get('is_toc_entry') or row.get('document_zone') in {'table_of_contents','list_of_tables','list_of_figures','references','appendices'}: continue
        heading = str(row.get('heading') or '').lower(); text = str(row.get('text') or '')
        if 'abstract' in heading: kind = 'abstract'
        elif re.search(r'objective|question|hypothes',heading): kind = 'research_logic'
        elif re.search(r'framework|theor',heading): kind = 'framework'
        elif row.get('source_kind') == 'table_row': kind = 'tables'
        elif re.search(r'method|design|sample|analysis',heading): kind = 'methods'
        elif re.search(r'result|discuss|conclu|recommend',heading) or re.search(r'\btable\s+\d',text,re.I): kind = 'interpretations'
        else: continue
        groups[kind].append(row)
    selected = []; omitted = {}; used = 0
    weights = {'abstract':.05,'research_logic':.15,'framework':.10,'methods':.15,'tables':.25,'interpretations':.30}
    for kind,weight in weights.items():
        # Spread interpretation evidence across chapters rather than taking a prefix.
        ordered = sorted(groups[kind],key=lambda r:(int(r.get('paragraph') or 0)))
        if kind == 'interpretations':
            by_chapter = defaultdict(list)
            for r in ordered: by_chapter[r.get('chapter_number')].append(r)
            ordered = []
            while any(by_chapter.values()):
                for chapter in sorted(by_chapter,key=lambda n:n or 0):
                    if by_chapter[chapter]: ordered.append(by_chapter[chapter].pop(0))
        subtotal = 0; skipped = 0
        for row in ordered:
            size = len(str(row.get('text') or ''))+150
            if subtotal+size > limit*weight or used+size > limit: skipped += 1; continue
            selected.append(row); subtotal += size; used += size
        if skipped: omitted[kind] = skipped
    return selected, {'omitted_rows_by_component':omitted,'evidence_complete':not omitted,'selected_rows':len(selected)}

async def run_final_consistency_audit(review: dict, rows: list[dict], checkpoints, config, progress_callback=None) -> dict:
    from .academic_ai_engine import _payload, _pid, _valid_issue, _finding_row
    from .supervisory_accuracy_guard import apply_accuracy_gate
    from .ai_schemas import AcademicReviewBatch
    from .context_guard import build_context_lock
    from .model_router import CostAwareAIProvider, ReviewStage
    from .provider_state import provider_checkpoint_context
    from .supervisory_voice import VOICE_CONTRACT
    ledger = build_results_ledger(rows)
    selected, coverage = final_audit_evidence(rows, int(os.getenv('AI_FINAL_INTEGRATION_MAX_CHARS','60000')))
    review['results_ledger'] = ledger
    summary = review.setdefault('summary',{})
    if not selected:
        summary.update({'guided_final_consistency_audit':False,'final_consistency_audit_status':'insufficient evidence'})
        raise ValueError('Final consistency audit has no readable research evidence.')
    selected_numbers = {r.get('paragraph') for r in selected}
    provider = CostAwareAIProvider(config)
    packet = {'section_key':'FINAL-CONSISTENCY','heading':'Final cross-chapter consistency audit',
        'paragraphs':[_payload(r) for r in selected], 'study_profile':ledger['study_profile'],
        'objectives_questions_hypotheses':[e for e in ledger['objectives_questions_hypotheses'] if e['source']['paragraph'] in selected_numbers],
        'results_ledger':[e for e in ledger['estimates'] if e['source']['paragraph'] in selected_numbers],
        'reviewed_chapters':summary.get('guided_chapters_completed'), 'evidence_coverage':coverage,
        'existing_findings':[{k:r.get(k) for k in ('finding_id','item','required_action','chapter_number')} for r in (review.get('internal_issue_ledger') or {}).get('findings',[])],
        'instruction':'Compare the abstract, objectives, questions, hypotheses, framework, methods, statistical tables, results interpretation, discussion, conclusions and recommendations. Report only NEW material contradictions or unsupported links with exact supplied paragraph IDs. Do not repeat existing comments. Permit model-estimated effects for appropriate regression and SEM. Never claim omitted evidence was reviewed. If scope is partial, assess the supplied scope and identify it accurately. Return one AcademicReviewBatch review with section_key FINAL-CONSISTENCY. No comment minimum.',
        'supervisory_voice':VOICE_CONTRACT}
    packet['instruction'] += ' Include every supplied paragraph ID in assessed_paragraph_ids after assessing the evidence, including adequate passages. Return a substantive section_assessment even when there are no new issues.'
    prompt = json.dumps(packet,ensure_ascii=False)
    route = provider.route_signature(stage=ReviewStage.FINAL_AUDIT,review_depth='standard',requested_model=config.openai_final_audit_model,requested_effort=config.openai_final_audit_reasoning_effort)
    digest = hashlib.sha256(('final-audit-v2.11|'+prompt+route).encode()).hexdigest()
    key = 'final-consistency-'+digest[:22]
    result = checkpoints.load_provider_result(key,expected_input_hash=digest)
    if result is None:
        if progress_callback: await progress_callback(96,'Checking the final links among objectives, results and conclusions')
        with provider_checkpoint_context(checkpoints,key):
            result = await provider.complete_json(model=config.openai_final_audit_model,system_prompt='You are an experienced thesis supervisor adjudicating cross-chapter evidence. '+VOICE_CONTRACT,
                user_prompt=prompt,schema_model=AcademicReviewBatch,purpose='final_cross_chapter_consistency',reasoning_effort=config.openai_final_audit_reasoning_effort,
                max_output_tokens=config.standard_audit_max_output_tokens,stage=ReviewStage.FINAL_AUDIT,review_depth='standard',allow_escalation=False)
    sections = result.data.get('reviews') or []
    if len(sections) != 1 or sections[0].get('section_key') != 'FINAL-CONSISTENCY' or not sections[0].get('section_assessment'):
        raise ValueError('Final consistency audit returned no valid substantive audit section.')
    expected_ids = {_pid(r) for r in selected}
    assessed_ids = set(sections[0].get('assessed_paragraph_ids') or [])
    if not expected_ids.issubset(assessed_ids):
        raise ValueError('Final consistency audit did not assess every supplied evidence paragraph. Saved chapter reviews are retained.')
    checkpoints.save_provider_result(key,result,input_hash=digest)
    index = {_pid(r):r for r in rows}; lock = build_context_lock(rows,summary)
    issues = []
    for section in sections:
        for raw in section.get('issues') or []:
            issue = _valid_issue(raw,index,lock,allowed_ids=expected_ids)
            if issue:
                issue['verification_status'] = 'final_cross_chapter_audit'
                issues.append(issue)
    issues, gate = apply_accuracy_gate(issues,index,rows)
    findings = [_finding_row(issue,index) for issue in issues]
    review.setdefault('academic_findings',[]).extend(findings)
    review['final_consistency_audit'] = {'status':'completed','coverage':coverage,'accuracy_gate':gate,'section_assessment':sections[0]['section_assessment'],'new_finding_count':len(findings),'evidence_hash':ledger['evidence_hash'],'usage':result.usage.model_dump()}
    summary.update({'guided_final_consistency_audit':True,'final_consistency_audit_status':'completed','final_consistency_evidence_complete':coverage['evidence_complete']})
    return review
