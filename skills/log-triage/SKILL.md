---
name: log-triage
description: Reconstruct the specified instance/request timeline before judging an operation.
---

# Log triage procedure

1. Confirm both the VM instance UUID and `req-<UUID>`. Preserve this pair in every scoped tool call across indexed partitions.
2. Read approved history for this pair as background, then call `get_instance_summary` and `get_timeline` for the same pair.
3. Separate observed facts from hypotheses. INFO lines can still carry lifecycle evidence.
4. Treat isolated warnings as weak signals. Look for repetition, ordering, and cross-module agreement.
5. Bounded timelines contain opening and terminal events; use scoped searches for omitted evidence. If no matching pair exists, return `uncertain` and ask an operator to verify both IDs. A missing request ID never authorizes an instance-wide fallback.
6. Do not access `anomaly_labels.txt`; labels belong only to the evaluation runner.
