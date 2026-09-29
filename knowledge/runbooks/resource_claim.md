# Compute resource claim investigation

Applicable signals: claim failed, no valid host, insufficient memory, disk, or vCPU.

Checks:

1. Compare requested resources with the reported host totals and allocations.
2. Distinguish scheduler placement failures from compute-node claim failures.
3. A `Claim successful` event weakens a capacity-exhaustion hypothesis for that attempt.
4. Confirm the instance and request IDs before linking events.

This document is operational guidance. It is not evidence that any event occurred.
