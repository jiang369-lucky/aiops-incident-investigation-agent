---
name: log-triage
description: Reconstruct an incident timeline before deciding whether an instance is anomalous.
---

# Log triage procedure

1. Confirm the dataset and VM instance identifier. Do not broaden the query to unrelated tenants.
2. Call `get_instance_summary` first, then `get_timeline` for the same instance.
3. Separate observed facts from hypotheses. INFO lines can still carry lifecycle evidence.
4. Treat isolated warnings as weak signals. Look for repetition, ordering, and cross-module agreement.
5. If no instance-scoped records exist, return `uncertain` and ask an operator to verify the ID.
6. Do not access `anomaly_labels.txt`; labels belong only to the evaluation runner.
