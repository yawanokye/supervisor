from app.ai_config import HybridAIConfig
from app.model_router import CostAwareAIProvider, ReviewStage, ProviderName


def _config(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('VPROF_ENABLE_OPENAI', 'true')
    monkeypatch.setenv('VPROF_ENABLE_DEEPSEEK', 'false')
    monkeypatch.setenv('VPROF_COMBINED_APP_PIPELINE', 'true')
    monkeypatch.setenv('OPENAI_CLEANING_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_SECTION_ANALYSIS_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_FINAL_SYNTHESIS_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL', 'gpt-5.6-terra')
    return HybridAIConfig.from_env()


def _hybrid_config(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('VPROF_ENABLE_OPENAI', 'true')
    monkeypatch.setenv('VPROF_ENABLE_DEEPSEEK', 'false')
    monkeypatch.setenv('VPROF_COMBINED_APP_PIPELINE', 'true')
    monkeypatch.setenv('OPENAI_CLEANING_MODEL', 'gpt-5.6-luna')
    monkeypatch.setenv('OPENAI_SECTION_ANALYSIS_MODEL', 'gpt-5.6-luna')
    monkeypatch.setenv('OPENAI_SECTION_ANALYSIS_FALLBACK_MODEL', 'gpt-5.6-luna')
    monkeypatch.setenv('OPENAI_EXPERT_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_FINAL_SYNTHESIS_MODEL', 'gpt-5.6-terra')
    monkeypatch.setenv('OPENAI_FINAL_SYNTHESIS_FALLBACK_MODEL', 'gpt-5.6-luna')
    monkeypatch.setenv('OPENAI_CLEANING_REASONING_EFFORT', 'low')
    monkeypatch.setenv('OPENAI_SECTION_ANALYSIS_REASONING_EFFORT', 'medium')
    monkeypatch.setenv('OPENAI_EXPERT_REASONING_EFFORT', 'high')
    return HybridAIConfig.from_env()


def test_phase_1_routes_to_cleaning_model(monkeypatch):
    router = CostAwareAIProvider(_config(monkeypatch))
    plan = router.plan(stage=ReviewStage.LANGUAGE_SCAN, review_depth='standard')
    assert plan.primary.provider is ProviderName.OPENAI
    assert plan.primary.model == 'gpt-5.6-terra'


def test_phase_2_routes_to_section_analysis_model(monkeypatch):
    router = CostAwareAIProvider(_config(monkeypatch))
    plan = router.plan(stage=ReviewStage.RESEARCH_INTENSIVE_REVIEW, review_depth='standard')
    assert plan.primary.provider is ProviderName.OPENAI
    assert plan.primary.model == 'gpt-5.6-terra'
    # The same provider/model must not be presented as its own fallback.
    assert plan.fallback is None


def test_phase_3_routes_to_final_synthesis_model(monkeypatch):
    router = CostAwareAIProvider(_config(monkeypatch))
    plan = router.plan(stage=ReviewStage.FINAL_AUDIT, review_depth='advanced')
    assert plan.primary.provider is ProviderName.OPENAI
    assert plan.primary.model == 'gpt-5.6-terra'
    assert plan.fallback is None


def test_phase_3_does_not_allow_luna_section_request_to_override_terra(monkeypatch):
    router = CostAwareAIProvider(_hybrid_config(monkeypatch))
    plan = router.plan(
        stage=ReviewStage.FINAL_AUDIT,
        review_depth='standard',
        requested_model='gpt-5.6-luna',
        requested_effort='medium',
    )
    assert plan.primary.model == 'gpt-5.6-terra'
    assert plan.primary.reasoning_effort == 'medium'
    assert plan.fallback.model == 'gpt-5.6-luna'
    assert plan.fallback.reasoning_effort == 'medium'


def test_hybrid_pipeline_honours_explicit_expert_section_route(monkeypatch):
    router = CostAwareAIProvider(_hybrid_config(monkeypatch))
    plan = router.plan(
        stage=ReviewStage.RESEARCH_INTENSIVE_REVIEW,
        review_depth='standard',
        requested_model='gpt-5.6-terra',
        requested_effort='high',
    )
    assert plan.primary.model == 'gpt-5.6-terra'
    assert plan.primary.reasoning_effort == 'high'
    assert plan.fallback.model == 'gpt-5.6-luna'
