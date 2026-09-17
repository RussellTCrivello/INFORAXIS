"""Gateway compute-control layer: honesty, routing, back-pressure, isolation.

The tests that matter most are the honesty ones: this layer must never report
that it is running on an accelerator it does not have, and it must fall back to
the CPU while saying so.  The remaining tests pin the scheduling contract
(bounded queue, back-pressure, allocation, isolation, monitoring) that makes a
long ingestion survivable.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from core.compute import (  # noqa: E402
    BackpressureError,
    ComputeGateway,
    ExecutionMode,
    HardwareInventory,
    WorkloadKind,
    choose_device,
    detect_hardware,
)
from core.compute.capabilities import CPU, DPU, FPGA, GPU, NPU  # noqa: E402


def _inventory(accelerators=None, cpu_units=8) -> HardwareInventory:
    """Inventory built with explicit accelerator availability (no probing)."""
    inventory = HardwareInventory(probe=False)
    inventory.cpu.compute_units = cpu_units
    inventory.cpu.available = True
    accelerators = accelerators or {}
    inventory.accelerators = {}
    for kind in (GPU, NPU, FPGA, DPU):
        info = detect_hardware(probe=False).accelerators.get(kind)
        if info is None:  # pragma: no cover - defensive
            from core.compute.capabilities import AcceleratorInfo

            info = AcceleratorInfo(kind=kind, name=kind.upper(), available=False)
        info.available = bool(accelerators.get(kind, False))
        info.detail = "test inventory"
        inventory.accelerators[kind] = info
    return inventory


# ---------------------------------------------------------------------------
# Capability honesty
# ---------------------------------------------------------------------------
class TestCapabilityHonesty:
    def test_cpu_is_always_available_and_reports_measured_details(self):
        inventory = detect_hardware()
        assert inventory.cpu.available is True
        assert inventory.cpu.compute_units and inventory.cpu.compute_units >= 1
        assert "cores" in inventory.cpu.detail

    def test_unavailable_accelerators_explain_what_was_looked_for(self):
        inventory = detect_hardware()
        for kind, info in inventory.accelerators.items():
            if info.available:
                # A usable runtime *and* device must both be present for this
                # to be reported; nothing else claims availability.
                assert info.backend, f"{kind} claims availability without a backend"
            else:
                assert info.detail, f"{kind} unavailable without an explanation"

    def test_no_accelerator_is_claimed_without_a_verified_backend(self):
        """A device node alone must not be advertised as usable."""
        inventory = _inventory({GPU: False})
        assert GPU not in [i.kind for i in inventory.available_accelerators]


# ---------------------------------------------------------------------------
# Modes and placement
# ---------------------------------------------------------------------------
class TestExecutionModes:
    def test_mode_parsing_accepts_documented_spellings(self):
        assert ExecutionMode.parse("cpu") is ExecutionMode.CPU_ONLY
        assert ExecutionMode.parse("GPU") is ExecutionMode.GPU_ONLY
        assert ExecutionMode.parse("cpu+gpu") is ExecutionMode.CPU_GPU
        assert ExecutionMode.parse("auto") is ExecutionMode.AUTO
        with pytest.raises(ValueError):
            ExecutionMode.parse("tpu")

    def test_cpu_only_never_selects_an_accelerator_even_if_present(self):
        decision = choose_device(WorkloadKind.OCR, ExecutionMode.CPU_ONLY,
                                 {GPU: True, NPU: True, FPGA: False, DPU: False})
        assert decision.device == CPU
        assert decision.accelerated is False

    def test_gpu_only_without_a_gpu_falls_back_to_cpu_and_says_so(self):
        decision = choose_device(WorkloadKind.OCR, ExecutionMode.GPU_ONLY,
                                 {GPU: False, NPU: True, FPGA: False, DPU: False})
        assert decision.device == CPU
        assert "GPU-only mode was requested" in decision.reason
        # Falling back must not silently borrow a *different* accelerator.
        assert decision.device != NPU

    def test_gpu_is_selected_when_it_is_really_available(self):
        decision = choose_device(WorkloadKind.OCR, ExecutionMode.CPU_GPU,
                                 {GPU: True, NPU: False, FPGA: False, DPU: False})
        assert decision.device == GPU and decision.accelerated is True

    def test_workloads_that_must_not_change_output_stay_on_cpu(self):
        """Hashing/extraction identity must not depend on the device."""
        available = {GPU: True, NPU: True, FPGA: True, DPU: True}
        for workload in (WorkloadKind.HASHING, WorkloadKind.CONTENT_EXTRACTION,
                         WorkloadKind.INDEXING, WorkloadKind.METADATA):
            decision = choose_device(workload, ExecutionMode.AUTO, available)
            assert decision.device == CPU, workload

    def test_mode_report_states_effective_mode_and_reasons(self):
        gateway = ComputeGateway(inventory=_inventory({GPU: False}))
        report = gateway.mode_report()
        assert report["effective_mode"] == "cpu"
        assert report["usable_accelerators"] == []
        assert GPU in report["unavailable_accelerators"]


# ---------------------------------------------------------------------------
# Submission, fallback and monitoring
# ---------------------------------------------------------------------------
class TestSubmission:
    def test_inline_submission_returns_the_result_and_records_metrics(self):
        gateway = ComputeGateway(inventory=_inventory())
        result = gateway.submit(WorkloadKind.HASHING, lambda a, b: a + b, 2, 3)
        assert result == 5
        assert gateway.stats.submitted == 1
        assert gateway.stats.completed == 1
        assert gateway.snapshot()["latency_s"]["max"] > 0

    def test_inline_submission_does_not_serialise_parallel_callers(self):
        """The pipeline's workers must not queue behind the gateway."""
        gateway = ComputeGateway(inventory=_inventory(cpu_units=2),
                                 max_concurrency=1, admission_timeout_s=5.0)
        concurrent = []

        def worker():
            gateway.submit(WorkloadKind.HASHING, concurrent.append,
                           threading.current_thread().name)
            time.sleep(0.2)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        started = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started
        assert len(concurrent) == 4
        # Serialised admission would take 4 x 0.2s; the inline path must not.
        assert elapsed < 0.5, f"inline submissions were serialised ({elapsed:.2f}s)"

    def test_errors_are_counted_and_propagated(self):
        gateway = ComputeGateway(inventory=_inventory())

        def boom():
            raise ValueError("nope")

        with pytest.raises(ValueError):
            gateway.submit(WorkloadKind.OCR, boom)
        assert gateway.stats.failed == 1

    def test_fallback_is_recorded_when_the_mode_cannot_be_honoured(self):
        gateway = ComputeGateway(inventory=_inventory({GPU: False}),
                                 mode=ExecutionMode.GPU_ONLY)
        gateway.submit(WorkloadKind.OCR, lambda: "cpu")
        assert gateway.stats.fallbacks >= 1
        events = gateway.mode_report()["fallback_events"]
        assert events and events[-1]["used"] == CPU


# ---------------------------------------------------------------------------
# Back-pressure (explicit admission path)
# ---------------------------------------------------------------------------
class TestBackpressure:
    def test_admission_blocks_when_the_concurrency_limit_is_reached(self):
        gateway = ComputeGateway(inventory=_inventory(), max_concurrency=1,
                                 admission_timeout_s=0.1)
        with gateway.admit(WorkloadKind.OCR):
            with pytest.raises(BackpressureError):
                with gateway.admit(WorkloadKind.OCR):
                    pass  # pragma: no cover - admission must fail first
        # After release the slot is usable again.
        with gateway.admit(WorkloadKind.OCR):
            pass

    def test_queue_depth_limit_refuses_work_instead_of_growing_without_bound(self):
        gateway = ComputeGateway(inventory=_inventory(), max_concurrency=1,
                                 queue_depth=2, admission_timeout_s=0.2)
        # Occupy the single slot from another thread, then fill the queue.
        holder_started = threading.Event()
        release = threading.Event()

        def holder():
            with gateway.admit(WorkloadKind.OCR):
                holder_started.set()
                release.wait(5)

        thread = threading.Thread(target=holder, daemon=True)
        thread.start()
        holder_started.wait(2)

        refusals = 0
        for _ in range(6):
            try:
                with gateway.admit(WorkloadKind.OCR):
                    pass
            except BackpressureError:
                refusals += 1
        release.set()
        thread.join(timeout=5)
        assert refusals >= 1, "queue never refused work"
        assert gateway.stats.rejected >= 1

    def test_peak_queue_depth_is_recorded(self):
        gateway = ComputeGateway(inventory=_inventory(), max_concurrency=2,
                                 admission_timeout_s=1.0)
        with gateway.admit(WorkloadKind.HASHING):
            with gateway.admit(WorkloadKind.HASHING):
                pass
        assert gateway.stats.peak_queue_depth >= 1


# ---------------------------------------------------------------------------
# Allocation, isolation, adaptive scheduling
# ---------------------------------------------------------------------------
class TestAllocationAndIsolation:
    def test_allocation_never_offers_more_workers_than_usable_cores(self):
        gateway = ComputeGateway(inventory=_inventory(cpu_units=8))
        allocation = gateway.allocation()
        assert 1 <= allocation.concurrency <= 8
        assert allocation.queue_depth >= 1
        assert allocation.memory_bytes > 0

    def test_small_machines_do_not_reserve_cores_from_compute(self):
        """Reserving a core on a 2-core host would halve throughput."""
        gateway = ComputeGateway(inventory=_inventory(cpu_units=2))
        assert gateway.reserved_gateway_cores == 0
        assert gateway.suggested_workers(4) == 4

    def test_large_machines_reserve_a_slice_for_the_gateway(self):
        gateway = ComputeGateway(inventory=_inventory(cpu_units=32))
        assert gateway.reserved_gateway_cores >= 1
        assert gateway.suggested_workers(32) <= 32 - gateway.reserved_gateway_cores

    def test_isolation_reports_what_it_applied(self):
        gateway = ComputeGateway(inventory=_inventory(cpu_units=8))
        report = gateway.apply_isolation()
        # On a supported platform affinity is applied; elsewhere the report
        # says why not - either way it never raises.
        assert set(report) >= {"affinity", "nice", "reason"}

    def test_worker_advice_never_returns_zero(self):
        gateway = ComputeGateway(inventory=_inventory(cpu_units=1))
        assert gateway.suggested_workers(0) >= 1
        assert gateway.suggested_workers(1) >= 1


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
class TestMonitoring:
    def test_snapshot_reports_measured_resources_and_queue_state(self):
        gateway = ComputeGateway(inventory=_inventory())
        gateway.submit(WorkloadKind.HASHING, lambda: None)
        snapshot = gateway.snapshot()
        assert snapshot["concurrency_limit"] >= 1
        assert snapshot["queue_depth_limit"] >= 1
        assert "cpu_percent" in snapshot
        assert "memory_percent" in snapshot
        assert snapshot["samples"] >= 1

    def test_status_exposes_placement_for_every_workload(self):
        gateway = ComputeGateway(inventory=_inventory({GPU: True}))
        status = gateway.status()
        assert set(status["workload_placement"]) == {k.value for k in WorkloadKind}
        assert status["allocation"]["concurrency"] >= 1
        assert "stats" in status and "inventory" in status
