"""Per-review processing preferences shared by the existing provider pipeline."""
from contextvars import ContextVar
from dataclasses import fields, replace

processing_options = ContextVar("review_processing_options", default={})


def batch_primary_enabled():
    return processing_options.get().get("mode") == "batch"


def processing_config(config, mode):
    if mode not in {"flex", "batch"}:
        return config
    models = {f.name:"gpt-6.1-sol" for f in fields(config)
              if f.name.startswith("openai_") and f.name.endswith("_model")}
    models.update(openai_fast_model="gpt-6-luna", openai_cleaning_model="gpt-6-luna")
    return replace(config, **models, primary_provider="openai", enable_openai_routing=True,
                   enable_deepseek_routing=False, provider_failover_enabled=False,
                   combined_app_pipeline_enabled=True)
