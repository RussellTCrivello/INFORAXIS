# Compute modes — the operator's processing policy

The compute mode decides **where processing workloads are allowed to execute**.
It is a user-controlled policy, not an internal implementation detail: it is
selected on the command line or in the project configuration, it is never
hard-coded, and it is never changed for you — not because hardware is missing,
not because the machine is loaded, and not because a faster path happens to be
free.

## Selecting a mode

### Command line

```bash
# All work on the CPU. No accelerator is used, ever.
python run_cli.py --compute-mode cpu --path DATA --source SRC --side SIDE

# GPU only (strict). Every workload with a GPU implementation must run on it.
python run_cli.py --compute-mode gpu --path DATA --source SRC --side SIDE

# Automatic routing (the default).
python run_cli.py --compute-mode auto --path DATA --source SRC --side SIDE

# Both worker sets running concurrently.
python run_cli.py --compute-mode cpu+gpu --path DATA --source SRC --side SIDE
```

`--compute-mode` is also accepted by the interactive flow, where it preselects
the mode and still opens the normal prompts:

```bash
python run_cli.py --compute-mode cpu
```

Accepted spellings: `cpu`, `cpu-only`, `gpu`, `gpu-only`, `cpu+gpu` (also
`both`, `hybrid`), `auto`, `automatic`.

### Project configuration

`data/settings.json` (the same value the Operations UI edits):

```json
{
  "processing": {
    "compute_mode": "cpu"
  }
}
```

The settings file is created from the settings model, so `compute_mode` is
present with its current value and can be edited directly.

### Precedence

Deterministic, highest first:

| # | Layer | Example |
|---|-------|---------|
| 1 | Command line | `--compute-mode cpu` |
| 2 | Environment | `COMPUTE_MODE=cpu` (set on the command line; used by CI and the measurement harness) |
| 3 | Project configuration | `processing.compute_mode` in `data/settings.json` |
| 4 | Default | `auto` |

A command-line selection always overrides the project configuration, and the
configuration always overrides the default. The layer that supplied the value is
reported at startup, so there is never any doubt about which one won:

```
[COMPUTE] Compute Mode: CPU-ONLY
[COMPUTE] Compute Mode Source: command line (--compute-mode cpu)
```

## What each mode guarantees

### `cpu` — CPU-ONLY

* Every workload executes on the CPU.
* No accelerator is used, even when a usable one is present.
* Configured CPU concurrency, affinity and resource limits are respected.
* The mode never switches to GPU on its own. `fallback: not applicable`.

### `gpu` — GPU-ONLY

* Every workload that **has** a GPU implementation must execute on the GPU.
* A workload that cannot be executed on the GPU is **refused** with a capability
  error naming the workload, the requested mode and the detected devices. It is
  never quietly handed back as a CPU result.
* If no usable accelerator is present, the run fails *before* processing starts,
  with an actionable message. Exit code `1`.
* Workloads with no GPU implementation at all — hashing, format identification,
  storage, indexing — are not substitutions: the CPU is the only implementation
  that exists for them. The table below is published by
  `core.compute.policy.workflow_summary()` and printed in the run report.
* CPU does the unavoidable work of any pipeline (I/O, orchestration, database
  writes). That is not a processing fallback.
* The explicit escape hatch, for the case where a CPU run is genuinely wanted
  under a GPU policy, is `COMPUTE_GPU_FALLBACK=1`. It is opt-in, it is recorded
  as a fallback event with its reason, and it is never applied silently.

### `cpu+gpu` — CPU+GPU

* CPU and GPU worker sets run concurrently, with independent limits and queues.
* Without an accelerator the mode still runs, and **says so**: the GPU worker set
  is empty and the startup banner reports it as degraded.

### `auto` — automatic routing

* Each workload is routed from measured capability and live resource state:
  workload type, device fit (including accelerator memory), CPU/GPU utilisation,
  queue depth, and measured performance.
* CPU and GPU work may run concurrently.
* Every decision is recorded (see below), so routing is observable rather than
  mysterious.

## What is recorded

Startup, per run:

```
Compute Mode: CPU-ONLY
Compute Mode Source: command line (--compute-mode cpu)
Selected Device: CPU (accelerators disabled by this policy)
Actual Device: per workload - recorded in the run results
Fallback: not applicable (no accelerator is ever used)
```

Per workload execution (in-memory ring + aggregates, bounded):

| Field | Meaning |
|-------|---------|
| `execution_mode` | the mode in force |
| `selected_device` / `actual_device` | where it was routed, and where it really ran |
| `processor` | backend that executed it |
| `duration_ms` | how long it took |
| `outcome` | `completed` / `failed` / `capability_error` |
| `fallback_reason` | why a different device ran it, when one did |

Per run, in the results (`--format json`, `compute` block): requested mode, its
source, strictness, actual devices with counts, per-workload placements,
fallback events and capability errors. The same selection is written to the
action log under `COMPUTE_MODE`.

## When the selection cannot be honoured

| Situation | Behaviour |
|-----------|-----------|
| `gpu` on a host with no accelerator | The run fails at startup, exit code `1`, with the detected hardware, the reason and the available alternatives. |
| `gpu` and a workload has no GPU backend | The workload is refused (`DeviceUnavailableError`); `capability_errors` is incremented; nothing is reported as completed. |
| `gpu` with `COMPUTE_GPU_FALLBACK=1` | Runs on the CPU and records a fallback event with the reason. |
| `cpu+gpu` with no accelerator | Runs, and reports the empty GPU worker set as degraded. |
| A device is present but has no backend for that stage | The placement is downgraded **explicitly**: the record shows the CPU as both selected and actual, with the reason. |
| Memory pressure or CPU saturation | Worker windows shrink; the **mode never changes**. |

## Verifying it

```bash
# Unit + contract tests for the policy, precedence and refusal behaviour
python -m pytest tests/unit/test_compute_mode_policy.py \
                 tests/unit/test_compute_gateway.py \
                 tests/integration/test_compute_control_contract.py

# Cross-mode evidence equivalence on a real corpus
# (records refusals instead of treating them as failures; every mode that runs
#  must match the bypass reference object for object)
python tools/scalability/validate_compute_modes.py --workdir /tmp/modes --files 500
```

## Implementation map

| Concern | Location |
|---------|----------|
| Mode model, precedence, support check, display, recording | `core/compute/policy.py` |
| Device routing rules and workload/device table | `core/compute/routing.py` |
| Placement, strict-mode refusal, metrics, isolation | `core/compute/gateway.py` |
| Hardware probes (CPU/GPU/NPU/FPGA/DPU) | `core/compute/capabilities.py` |
| Back-pressure and worker windows | `core/compute/backpressure.py` |
| CLI flag, fail-fast, result record | `apps/cli/main.py`, `run_cli.py` |
| Web startup banner | `run_web.py` |
