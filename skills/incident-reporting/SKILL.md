---
name: incident-reporting
description: Produce a concise investigation report and keep external actions behind human approval.
---

# Incident reporting procedure

The report must contain: instance ID, request ID, verdict, confidence, observed summary, candidate hypothesis, supporting log evidence,
counterevidence, Runbook sources for recommended checks, limitations, and `requires_human_review=true`.

Use `anomalous` only when failure/error signals or a calibrated latency outlier are present. Use `normal` only when relevant
records exist and configured suspicious signals are absent. Otherwise use `uncertain`.

Keep conclusions within this request. Historical drafts are background, and missing/truncated observations remain limitations rather than evidence that no failure occurred.

The system performs read-only investigation. An approved draft may be saved in PostgreSQL for this
instance/request pair only after the human caller explicitly sets `approved=true`.
