# Environment changes – v1.9.9.1

No breaking environment change is required.

Recommended explicit settings:

```env
VPROF_DETERMINISTIC_SUPERVISORY_CHECKLIST=true
VPROF_DETERMINISTIC_CHECKLIST_MAX_ISSUES=36
VPROF_HARD_SUPERVISORY_CHECKLIST=true
VPROF_DOCX_NO_TITLEPAGE_FALLBACK=true
```

The new settings document behaviour now enabled by default: hard supervisory checks and no title-page fallback anchoring for unresolved comments.
