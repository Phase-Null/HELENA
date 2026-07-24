---
tags: [architecture, runtime]
date: 2026-03-05
status: active
component: helena_core/runtime/
bugs: [11, 20, 21]
---

# Runtime — Resource Management, Gaming Optimizer, and Hardware Detection

HELENA's runtime system manages CPU, RAM, GPU, disk IO, and network IO resources. It includes hardware detection, gaming compatibility mode, and resource throttling.

> [!tip] Key Limits
> - CPU cap: **85%** (`cpu_limit_percent = 85.0`)
> - RAM cap: **85%** of total (`ram_limit_mb = int(total_ram * 0.85)`)

---

## ResourceManager (`helena_core/runtime/resources.py`)

Manages system resources and enforces limits.

### ResourceType (Enum)

| Type | Purpose |
|------|---------|
| CPU | Processor utilization |
| GPU | Graphics processor |
| RAM | Memory consumption |
| VRAM | GPU memory |
| DISK_IO | Disk read/write throughput |
| NETWORK_IO | Network bandwidth |
| THERMAL | CPU/GPU temperature |

### ResourceUsage (dataclass)

| Field | Type | Purpose |
|-------|------|---------|
| `cpu_percent` | `float` | Current CPU utilization |
| `gpu_percent` | `float` | GPU utilization |
| `ram_mb` | `int` | RAM used in MB |
| `vram_mb` | `int` | VRAM used in MB |
| `disk_io_mbps` | `float` | Disk IO rate |
| `network_io_mbps` | `float` | Network IO rate |
| `cpu_temp_c` | `Optional[float]` | CPU temperature |
| `gpu_temp_c` | `Optional[float]` | GPU temperature |

> [!warning] Bug #11 — Disk/Network IO Are Cumulative Counters, Not Rates
> `psutil` counters return cumulative bytes since boot, not instantaneous rates. All IO-based limit checks become meaningless after uptime. Fix: track previous IO counters, calculate `delta_bytes / delta_time` for MB/s rate. See [[Bug Fixes Registry#Bug 11]].

### ThrottleAction (Enum)

`NONE → REDUCE_CPU → REDUCE_GPU → SUSPEND_PROCESS → TERMINATE_PROCESS → REDUCE_PRIORITY`

---

## Hardware Detection (`helena_core/runtime/hardware.py`)

Detects system capabilities at startup. Returns `HardwareProfile` with:
- CPU cores, clock speed, model name
- Total RAM, available RAM
- GPU model, VRAM (if available)
- Disk space, disk type (SSD/HDD)

---

## GamingOptimizer (`helena_core/runtime/gaming.py`)

Throttles HELENA's resource usage when games are detected (config: `gaming_compat: true`).

| Behavior | When Game Detected |
|----------|-------------------|
| CPU limit | Reduced from 85% → 50% |
| RAM limit | Reduced to leave headroom |
| Training | Suspended during gaming |
| Background tasks | Paused |

> [!warning] Bug #20 — Memory Reservation Not Implemented
> Game memory reservation code is missing (line 390). Should allocate `bytearray` with `MemoryError` handling. See [[Bug Fixes Registry#Bug 20]].

---

## ProfileManager (`helena_core/runtime/profiles.py`)

Hardware profiles define resource limits per tier:

| Profile | CPU Limit | RAM Limit | GPU | Use Case |
|---------|-----------|-----------|-----|----------|
| Default | 85% | 85% of total | disabled | Standard operation |
| Gaming | 50% | Reduced | shared | Game detected |
| Performance | 100% | 95% | enabled | Training/benchmarking |
| Efficiency | 60% | 60% | disabled | Idle/background |

---

## Bug #21 — Logger API Mismatch Throughout Runtime

`logger.info("Tag", "Message")` — the actual message is **SILENTLY DROPPED** because standard Python logging uses `(message, *args)`. The first arg is treated as format string, second as substitution. Fix: replace with `logger.info("[Tag] Message")`. See [[Bug Fixes Registry#Bug 21]].

---

## Related Notes

- [[Kernel]] — runtime initialized alongside kernel
- [[Training Pipeline]] — training suspended during gaming mode
- [[Config Reference]] — runtime config settings
