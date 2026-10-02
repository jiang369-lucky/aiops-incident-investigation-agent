---
name: evidence-verification
description: Build a citeable evidence chain and actively search for observations that weaken it.
---

# Evidence verification procedure

1. Every incident fact must cite a `dataset:line` identifier retrieved for the locked instance/request pair.
2. Compare failures with successful events in this same request. A successful claim supports allocation success; HTTP 200 supports only API response success; successful spawn weakens a build-failure hypothesis but does not disprove slow build.
3. Run `validate_evidence` with both IDs before finishing, including new supporting and counterevidence citations from supplemental searches. Retain only citations validated for this pair.
4. Cite retrieved Runbook chunks separately as guidance; never use them as proof that an event occurred.
5. If the evidence supports multiple explanations, list a candidate hypothesis and mark it for review.
6. Never turn correlation into a confirmed root cause.
