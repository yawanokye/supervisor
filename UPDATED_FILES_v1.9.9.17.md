# Updated files v1.9.9.17

This update makes the VProfessor methods, results and discussion audit generic rather than tailored to the example PhD study used for testing.

## Updated files

- `app/thorough_review.py`
- `app/academic_ai_engine.py`
- `app/ai_prompts.py`
- `.env.example`
- `vprofessor-openai-worker.env.example`
- `tests/test_generic_method_results_review_v19917.py`

## Behavioural changes

- Detects the actual analysis route from the uploaded work before applying checks.
- Supports quantitative, qualitative, mixed-methods, review, experimental, econometric, SEM, mediation and moderation workflows.
- Applies method-specific checks only when that analysis is present.
- Does not assume classroom incivility, academic entitlement, perceived academic support, PROCESS Model 3 or any other construct from the test thesis.
- Gives evidence-preserving guidance: missing analyses are recommended as required corrections, not invented as completed results.

## Examples of generic checks

- Regression: model choice, assumptions, diagnostics, R²/F/t/p/CI consistency and causal-language limits.
- SEM/PLS-SEM: measurement model, structural model, reliability, validity, bootstrapping and fit/predictive evidence.
- Moderation: interaction term, R² change, conditional effects, simple slopes and interaction plots where applicable.
- Mediation: indirect effect, bootstrapped confidence interval, direct and total effects where applicable.
- Qualitative: coding procedure, theme development, participant quotations and trustworthiness.
- Mixed methods: integration, triangulation, joint displays and meta-inferences.
- Panel/time series/econometric analysis: estimator choice and model-specific diagnostics.
- Review-based research: search strategy, screening, inclusion/exclusion criteria and appraisal.

## Tests

Targeted generic audit, statistical review, comment-depth and routing tests passed.
