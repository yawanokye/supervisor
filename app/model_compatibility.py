"""Model IDs remain operator-controlled. Adapt parameters, never silently substitute a model."""
from __future__ import annotations
import json
import os
import re

_EFFORTS = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']

def capabilities(model: str) -> dict:
    value = model.lower()
    if any(token in value for token in ('embedding', 'whisper', 'tts-', 'dall-e', 'gpt-image', 'moderation', 'transcribe')):
        raise ValueError(f'{model} is not a text-review model. Configure a text-generating OpenAI model.')
    reasoning = value.startswith(('gpt-5', 'gpt-6', 'o1', 'o3', 'o4'))
    efforts = _EFFORTS[:]
    if value.startswith(('gpt-6.1-sol', 'gpt-6-astra')): efforts = ['low','medium','high','xhigh','max']
    elif value.startswith(('o1','o3','o4')): efforts = ['low','medium','high']
    elif value.startswith('gpt-5') and not value.startswith(('gpt-5.1','gpt-5.2','gpt-5.4','gpt-5.5','gpt-5.6')): efforts = ['minimal','low','medium','high']
    result = {'endpoint': 'chat' if value.startswith(('gpt-3.5', 'gpt-4-')) or value == 'gpt-4' else 'responses',
        'reasoning': reasoning, 'efforts': efforts, 'structured': not value.startswith(('gpt-3.5', 'gpt-4-')),
        'vision': not value.startswith(('gpt-3.5','o1-mini','o3-mini')) and value != 'gpt-4', 'background': reasoning}
    try:
        override = json.loads(os.getenv('OPENAI_MODEL_CAPABILITIES_JSON', '{}')).get(model, {})
        if isinstance(override, dict): result.update(override)
    except (ValueError, TypeError):
        pass
    return result

def compatible_effort(model: str, requested: str) -> str | None:
    caps = capabilities(model)
    if not caps['reasoning']: return None
    value = requested.lower() if requested else 'medium'
    if value in caps['efforts']: return value
    rank = _EFFORTS.index(value) if value in _EFFORTS else 3
    return min(caps['efforts'], key=lambda e: abs(_EFFORTS.index(e) - rank))

def adapt_rejected_parameter(body: dict, error: str) -> bool:
    """Only explicit compatibility 400s may modify a request."""
    low = str(error).lower()
    if 'http 400' not in low: return False
    if ('image' in low) and ('not supported' in low or 'unsupported' in low):
        changed = False
        for item in body.get('input', []):
            if isinstance(item.get('content'), list):
                kept = [c for c in item['content'] if c.get('type') != 'input_image']
                changed = changed or len(kept) != len(item['content'])
                item['content'] = kept
        if changed:
            body['input'][0]['content'] += '\nVisual evidence was unavailable to this model. Do not claim to verify diagram pixels, arrows or legibility. Request manual visual verification when needed.'
            return True
    if ('reasoning.effort' in low or 'reasoning_effort' in low) and 'reasoning' in body:
        supported = [e for e in _EFFORTS if re.search(r"['\"]"+e+r"['\"]", low)]
        current = body['reasoning'].get('effort','medium')
        if supported:
            rank = _EFFORTS.index(current) if current in _EFFORTS else 3
            new = min(supported, key=lambda e: abs(_EFFORTS.index(e)-rank))
            if new != current: body['reasoning']['effort'] = new; return True
        body.pop('reasoning', None); return True
    for parameter in ('reasoning','background','prompt_cache_key','store'):
        if parameter in low and parameter in body and ('unsupported' in low or 'not supported' in low):
            body.pop(parameter); return True
    if ('json_schema' in low or 'text.format' in low or 'response_format' in low) and ('not supported' in low or 'unsupported' in low):
        if body.get('text',{}).get('format',{}).get('type') == 'json_schema':
            body['text']['format'] = {'type':'json_object'}; return True
        if 'text' in body: body.pop('text'); return True
    return False
