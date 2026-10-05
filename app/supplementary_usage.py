"""Include final integration and prose editing in the existing usage accounting."""
def append_usage(snapshot: dict, usage: dict) -> dict:
    if not usage: return snapshot
    records = snapshot.setdefault('usage', [])
    key = lambda r: (r.get('request_id'),r.get('purpose'),r.get('model'),r.get('input_tokens'),r.get('output_tokens'))
    if key(usage) not in {key(r) for r in records}:
        records.append(dict(usage))
    snapshot['estimated_cost_usd'] = round(sum(float(r.get('estimated_cost_usd') or 0) for r in records),6)
    snapshot['api_call_count'] = len(records)
    return snapshot
