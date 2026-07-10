# VProfessor v1.9.9.15, Sequential red references and specific corrections

Updated files:

- `app/annotated_exporter.py`
  - Adds global sequential reference numbers across the reviewed chapter.
  - Inserts red `[n]` reference markers beside the exact sentence or paragraph where the native comment applies.
  - Uses the same number inside the native Word comment box.
  - Keeps grouped native comments where findings share the same exact evidence span, but avoids broad merging that makes location tracking difficult.
  - Adds a blue inline end-of-chapter section titled `Specific corrections required`.
  - Lists each numbered correction with context-specific guidance and examples using `For example, ...`.
  - Keeps missing-section findings in the end-of-chapter blue correction list instead of attaching them to unrelated existing sections.

- `app/inline_annotated_exporter.py`
  - Applies the same sequential numbering logic to the inline annotated DOCX.
  - Adds red `[n]` markers beside marked text and blue inline supervisor comments.
  - Adds the same `Specific corrections required` blue end-of-chapter list.

- `.env.example`
  - Adds `VPROF_SEQUENTIAL_COMMENT_REFERENCES=true`.
  - Adds `VPROF_SPECIFIC_CORRECTIONS_REQUIRED_BOTTOM=true`.

- `vprofessor-openai-worker.env.example`
  - Adds the same environment variables for the background worker.

- `tests/test_native_comment_export_v187.py`
  - Updates export tests for sequential red reference markers and the new `Specific corrections required` blue checklist.

Branding note:

- `Meet V-Prof Priscilla Boafowaa Oppong` was not changed.
