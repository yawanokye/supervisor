# V-Professor 2.7.0 Final Professional Review

This release completes the quality controls identified through example-document testing without internalising any example topic, institution, location, construct or correction as a production rule.

## Main corrections

- Natural comments are limited to focused supervisory prose and no longer expose reviewer-prompt labels.
- Comments prefer the exact substantive paragraph instead of a nearby section heading.
- Duplicate root causes are consolidated before numbering.
- Canonical report findings and native Word comments are strictly reconciled before export.
- Previous source comments are kept separate, empty comments are removed, and obvious restored sections may be marked as addressed.
- Generic limitations are reviewed for their consequences for evidence and conclusions.
- Unsupported absolute claims receive proportionate academic-language corrections.
- Concise but accurate chapter outlines are not criticised merely for being brief.
- Deterministic evidence-locked findings are retained when broader AI findings are merged.

## Isolation guarantee

The review rules operate on the current submission. Example documents are test evidence only and do not become reusable topic-specific rules.

## Deployment

Deploy the same package to the web service and worker. Use a new review job because the pipeline, checkpoint and export identifiers changed in version 2.7.0.
