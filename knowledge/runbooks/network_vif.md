# Network and VIF investigation

Applicable signals: network-vif-plugged, VIF timeout, port binding failure, connection refused.

Checks:

1. Follow the same request and instance through API, scheduler, compute, and network messages.
2. Check whether a VIF-plugged event arrived before the build completed.
3. Do not infer a network root cause from a missing message alone; the dataset may be incomplete.
4. Request Neutron and switch telemetry during human review when OpenStack Nova logs are insufficient.

This document is operational guidance. It is not evidence that any event occurred.
