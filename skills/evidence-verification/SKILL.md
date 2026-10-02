---
name: evidence-verification
description: Build a citeable evidence chain and actively search for observations that weaken it.
---

# Evidence verification procedure

1. Every incident fact must cite a `dataset:line` identifier returned by a log tool.
2. Search for counterevidence such as successful resource claims, HTTP 200 responses, or a successful spawn.
3. Run `validate_evidence` before finishing. Remove missing or wrong-instance citations.
4. Cite retrieved Runbook chunks separately as guidance; never use them as proof that an event occurred.
5. If the evidence supports multiple explanations, list a candidate hypothesis and mark it for review.
6. Never turn correlation into a confirmed root cause.
