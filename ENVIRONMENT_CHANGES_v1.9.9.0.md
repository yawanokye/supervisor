# Environment changes - v1.9.9.0

No key change is required for existing deployments, but the following settings are now available:

```env
VPROF_DETERMINISTIC_SUPERVISORY_CHECKLIST=true
VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES=36
```

Keep `VPROF_DETERMINISTIC_SUPERVISORY_CHECKLIST=true` for MPhil, Professional Doctorate and PhD review. Increase `VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES` only if you want the DOCX to carry more checklist-triggered comments.
