# OpenStack VM lifecycle investigation

Applicable signals: VM Stopped, VM Paused, VM Resumed, instance spawned successfully, build timeout.

Checks:

1. Reconstruct the ordering of claim, image creation, VIF plug, lifecycle, and spawn-complete events.
2. A pause/resume during creation may be transient; repeated stop/pause without a later successful state is stronger.
3. Correlate with the request ID and compute host before attributing the problem to the hypervisor.
4. Preserve successful-spawn messages as counterevidence.
5. Compare build duration with a baseline derived only from normal instances; latency outliers may be
   anomalous even when all lines are logged at INFO level.

This document is operational guidance. It is not evidence that any event occurred.
