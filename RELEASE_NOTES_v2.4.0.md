# V-Professor 2.4.0 Final Natural-Comment Update

## What changed

1. Word comments and inline annotations now read as natural supervisory prose. Mechanical internal labels are removed.
2. Findings on the same paragraph are combined in one numbered comment box.
3. Export reconciliation confirms that every released finding is represented in native comments.
4. Whole-section contradiction checks prevent false claims that chapter introductions, objectives, applied contributions or other visible elements are missing.
5. Repeated local-context, problem-gap, significance, terminology and alignment findings are consolidated before numbering.
6. British/American spelling findings use only spellings actually present in the submitted work.
7. Deterministic checks now detect title-purpose relationship drift, study-setting drift and modal-verb errors in research questions.
8. Existing OpenAI and DeepSeek provider selection, cost controls and adaptive DeepSeek truncation recovery are retained.

## Benchmark

The previously generated 32-item Chapter One assessment was reprocessed through the 2.4.0 release guard. It produced 10 distinct corrections. The false claims about a missing introduction, an unacceptable `CHAPTER ONE` heading, a missing third objective and an absent applied contribution were removed. Repeated background, problem-statement and significance comments were consolidated.

## Deployment

Deploy the complete package to both the web service and background worker. Apply the same provider environment variables to both services. Submit unfinished or failed reviews as new jobs because the 2.4.0 pipeline identifiers differ from earlier releases.
