class NetworkMonitor(BaseAgent):
    # Core logic shared by all variants

class NetworkMonitorV1(NetworkMonitor):
    threshold = 0.3      # sensitive
    interval = 5         # seconds
    signatures = RULESET_ALPHA

class NetworkMonitorV2(NetworkMonitor):
    threshold = 0.5      # balanced
    interval = 8
    signatures = RULESET_BETA

class NetworkMonitorV3(NetworkMonitor):
    threshold = 0.7      # conservative
    interval = 12
    signatures = RULESET_GAMMA

class NetworkMonitorV4(NetworkMonitor):
    threshold = 0.4      # adaptive
    interval = 3         # fastest
    signatures = RULESET_DELTA
```

Each variant also has a slightly randomized jitter on its timing so they don't all scan simultaneously — staggered coverage with no predictable gap.

---

**Communication architecture:**

Agents don't talk to each other — they report only to HELENA. HELENA correlates their reports and builds situational awareness. This prevents a compromised agent from poisoning others.
```
Agent → Report → HELENA's SecurityContext → Assessment → Decision → Action
