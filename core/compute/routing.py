"""Execution modes and workload routing for the compute gateway.

The routing table is the honest contract of this layer: it says which
execution devices a workload *may* use, and the gateway refuses to place a
workload on a device whose backend is not present and verified on this machine.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from .capabilities import CPU, DPU, FPGA, GPU, NPU


class ExecutionMode(str, enum.Enum):
    """Execution modes selectable by configuration or per request."""

    CPU_ONLY = "cpu"
    GPU_ONLY = "gpu"
    CPU_GPU = "cpu+gpu"
    AUTO = "auto"

    @classmethod
    def parse(cls, value) -> "ExecutionMode":
        if isinstance(value, cls):
            return value
        text = (str(value or "auto").strip().lower()
                .replace("_", "").replace("-", "").replace("+", "").replace(" ", ""))
        aliases = {
            "cpu": cls.CPU_ONLY, "cpuonly": cls.CPU_ONLY, "cpumode": cls.CPU_ONLY,
            "gpu": cls.GPU_ONLY, "gpuonly": cls.GPU_ONLY, "gpumode": cls.GPU_ONLY,
            "cpugpu": cls.CPU_GPU, "both": cls.CPU_GPU, "hybrid": cls.CPU_GPU,
            "auto": cls.AUTO, "automatic": cls.AUTO,
        }
        if text not in aliases:
            raise ValueError(f"Unknown execution mode {value!r}; expected one of "
                             f"{[m.value for m in cls]}")
        return aliases[text]


class WorkloadKind(str, enum.Enum):
    """Compute-intensive stages the pipeline can route."""

    HASHING = "hashing"
    CONTENT_EXTRACTION = "content_extraction"
    OCR = "ocr"
    CLASSIFICATION = "classification"
    INDEXING = "indexing"
    COMPRESSION = "compression"
    METADATA = "metadata"


#: Devices each workload may run on, in preference order.  A workload appears
#: here only with the devices whose *results are identical* to the CPU path
#: (the pipeline's extraction fidelity and accuracy requirements forbid a
#: device that would change output).  Hashing, for example, is digest-exact on
#: any device that can compute SHA-256 over the same bytes.
WORKLOAD_DEVICES: Dict[WorkloadKind, FrozenSet[str]] = {
    WorkloadKind.HASHING: frozenset({CPU}),
    WorkloadKind.CONTENT_EXTRACTION: frozenset({CPU}),
    WorkloadKind.OCR: frozenset({CPU, GPU, NPU}),
    WorkloadKind.CLASSIFICATION: frozenset({CPU, GPU, NPU}),
    WorkloadKind.INDEXING: frozenset({CPU}),
    WorkloadKind.COMPRESSION: frozenset({CPU}),
    WorkloadKind.METADATA: frozenset({CPU}),
}

#: Accelerator kinds the gateway knows how to probe (and will only use when a
#: verified backend exists on this machine).
KNOWN_ACCELERATORS = (GPU, NPU, FPGA, DPU)


@dataclass
class DeviceDecision:
    """Where a workload will run, and why."""

    workload: WorkloadKind
    device: str
    backend: str
    reason: str
    accelerated: bool = False

    def as_dict(self) -> Dict[str, object]:
        return {
            "workload": self.workload.value,
            "device": self.device,
            "backend": self.backend,
            "accelerated": self.accelerated,
            "reason": self.reason,
        }


def mode_allows(mode: ExecutionMode, device: str) -> bool:
    """True when ``mode`` may execute on ``device`` (CPU is the fallback)."""
    if device == CPU:
        return True
    return device in accelerator_priority(mode)


def allowed_devices(workload: WorkloadKind) -> FrozenSet[str]:
    return WORKLOAD_DEVICES.get(workload, frozenset({CPU}))


def accelerator_priority(mode: ExecutionMode) -> tuple:
    """Accelerator kinds to try, in order, for ``mode``.

    ``gpu`` and ``cpu+gpu`` mean the GPU specifically, so no other accelerator
    may be substituted.  ``auto`` considers every accelerator kind.
    """
    if mode in (ExecutionMode.GPU_ONLY, ExecutionMode.CPU_GPU):
        return (GPU,)
    if mode is ExecutionMode.AUTO:
        return (GPU, NPU, FPGA, DPU)
    return ()


def choose_device(
    workload: WorkloadKind,
    mode: ExecutionMode,
    available: Optional[Dict[str, bool]] = None,
) -> DeviceDecision:
    """Pick a device for ``workload`` under ``mode``.

    ``available`` maps accelerator kind -> usability (as measured by the
    capability probes).  The function never selects a device that is not both
    allowed for the workload and present; when the requested mode cannot be
    honoured it falls back to the CPU and says so in ``reason`` rather than
    pretending.  Reaching this function's CPU branch is therefore always an
    explicit, explainable outcome.
    """
    available = available or {}
    permitted = allowed_devices(workload)

    for device in accelerator_priority(mode):
        if device not in permitted or not available.get(device, False):
            continue
        return DeviceDecision(workload=workload, device=device,
                              backend=f"{device} backend",
                              reason=f"{device} execution", accelerated=True)

    # CPU is always permitted: it is the defined fallback for every workload.
    if mode is ExecutionMode.GPU_ONLY:
        reason = ("CPU fallback: GPU-only mode was requested but no verified GPU "
                  "execution path is available for this workload")
    elif mode is ExecutionMode.CPU_GPU:
        reason = ("CPU execution: CPU+GPU mode was requested, but no verified "
                  "accelerator path is available for this workload")
    else:
        reason = "CPU execution"
    return DeviceDecision(workload=workload, device=CPU, backend="stdlib",
                          reason=reason, accelerated=False)

# Nothing selectable: the workload's device set is empty (defensive).
    return DeviceDecision(workload=workload, device=CPU, backend="stdlib",
                          reason="no permitted device; defaulting to CPU",
                          accelerated=False)
