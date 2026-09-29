---
name: incident-reporting
description: Produce a concise investigation report and keep external actions behind human approval.
---

# Incident reporting procedure

The report must contain: verdict, confidence, observed summary, candidate hypothesis, supporting evidence,
counterevidence, recommended checks, limitations, and `requires_human_review=true`.

Use `anomalous` only when repeated failure/error signals are present. Use `normal` only when relevant
records exist and configured suspicious signals are absent. Otherwise use `uncertain`.

Never restart a VM, change infrastructure, or open an external ticket. A local ticket draft may be saved
only after the human caller explicitly sets `approved=true`.
