from pathlib import Path

import pytest

from app.ai_config import HybridAIConfig
from app.ai_schemas import AIUsageRecord
from app.model_compatibility import capabilities, compatible_effort
from app.model_router import CostAwareAIProvider, ReviewStage


def router(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setenv('VPROF_ENABLE_OPENAI','true')
    monkeypatch.setenv('VPROF_ENABLE_DEEPSEEK','false')
    for key in ('OPENAI_MODEL_PRICES_JSON','PRICE_OPENAI_61_SOL_INPUT','PRICE_OPENAI_61_SOL_CACHED_INPUT',
        'PRICE_OPENAI_61_SOL_OUTPUT','PRICE_OPENAI_6_LUNA_INPUT','PRICE_OPENAI_6_LUNA_CACHED_INPUT','PRICE_OPENAI_6_LUNA_OUTPUT'):
        monkeypatch.delenv(key,raising=False)
    return CostAwareAIProvider(HybridAIConfig.from_env())


def test_current_standard_luna_and_sol_rates(monkeypatch):
    config=router(monkeypatch).config
    assert config.openai_prices_for_model('gpt-6-luna') == (.10,.01,.50)
    assert config.openai_prices_for_model('gpt-6.1-sol') == (2,.10,10)


def test_cache_writes_are_distinct_from_ordinary_input_and_cache_reads(monkeypatch):
    provider=router(monkeypatch)
    usage=AIUsageRecord(provider='openai',model='gpt-6.1-sol',purpose='test',
        input_tokens=10000,cached_input_tokens=4000,cache_write_input_tokens=2000,output_tokens=1000)
    # 4K ordinary * $2 + 4K cached * $.10 + 2K written * $2.50 + 1K output * $10.
    assert provider._price_usage(usage).estimated_cost_usd == pytest.approx(.0234)


def test_long_context_rates_apply_to_the_whole_individual_request(monkeypatch):
    provider=router(monkeypatch)
    usage=AIUsageRecord(provider='openai',model='gpt-6.1-sol',purpose='test',
        input_tokens=300000,cached_input_tokens=100000,cache_write_input_tokens=50000,output_tokens=1000)
    assert provider._price_usage(usage).estimated_cost_usd == pytest.approx(.885)


def test_combined_usage_retains_cache_write_counts_without_repricing_an_aggregate(monkeypatch):
    provider=router(monkeypatch)
    one=AIUsageRecord(provider='openai',model='gpt-6-luna',purpose='first',
        input_tokens=200000,cache_write_input_tokens=200000)
    combined=provider._combine_usage(one,one,purpose='combined')
    assert combined.cache_write_input_tokens == 400000
    assert combined.estimated_cost_usd == pytest.approx(.05)


def test_luna_uses_only_documented_reasoning_efforts():
    assert capabilities('gpt-6-luna')['efforts'] == ['none','low','medium','high','xhigh','max']
    assert compatible_effort('gpt-6-luna','minimal') in {'none','low'}


def test_optional_profile_routes_mechanical_and_academic_work_to_different_models(monkeypatch):
    router(monkeypatch)
    for line in Path('vprofessor-gpt6-hybrid.env.example').read_text().splitlines():
        if line and not line.startswith('#'):
            key,value=line.split('=',1);monkeypatch.setenv(key,value)
    monkeypatch.setenv('VPROF_COMBINED_APP_PIPELINE','true')
    provider=CostAwareAIProvider(HybridAIConfig.from_env())
    assert provider.plan(stage=ReviewStage.LANGUAGE_SCAN).primary.model == 'gpt-6-luna'
    assert provider.plan(stage=ReviewStage.STANDARD_REVIEW).primary.model == 'gpt-6.1-sol'
    assert provider.plan(stage=ReviewStage.FINAL_AUDIT).primary.model == 'gpt-6.1-sol'
