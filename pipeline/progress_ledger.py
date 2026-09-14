"""Dynamic work ledger for real-time processing progress.

WHY THIS EXISTS
---------------
Progress used to be a pair of integers on ``IntegratedFileReader``
(``_processing_stats['total']`` / ``['completed']``). That model is only
correct for a flat folder of top-level files, and the pipeline is not flat:

* ``total`` was set once, in ``process_folder()``, from ``read_tree()`` - so it
  only ever counted files visible on the filesystem before processing began.
  Archive members, email attachments and embedded Office/OpenDocument objects
  are materialised *later*, by a reader, and never entered the denominator.
* Nested children are processed by a **second** ``IntegratedFileReader`` built
  inside ``FileRouterService._process_extracted_files()``. That reader had its
  own private counters and no ``progress_callback``, so every nested file was
  invisible to the job the user was watching.
* ``completed`` was incremented in the *join* loop of ``_process_with_threads``,
  which joins threads in submission order. One slow container in slot 0 held
  the counter at 0 even after every other worker had finished.

The net effect was the reported symptom: 0% for the entire run, then a jump to
100%.

This ledger replaces those counters with a single shared, thread-safe record of
work that **grows as containers are opened**. One ledger per user-visible job;
it is handed down the processing chain exactly the way ``storage_pipeline``
already is, so parents and children account into the same denominator.

ACCOUNTING RULES
----------------
1. *Discovery* adds work: ``add_discovered(n, key=...)``. ``key`` makes
   discovery idempotent - the router registers an extraction directory when it
   finds it, and the nested reader re-registers the same directory with its
   post-checkpoint count; the second call reconciles the difference instead of
   double-counting.
2. *Every* unit that enters the pipeline is opened with ``begin()`` and closed
   exactly once with ``WorkUnit.settle(outcome)``. Settlement is idempotent, so
   a worker that is abandoned on timeout and later finishes anyway cannot be
   counted twice.
3. Terminal outcomes are ``completed``, ``failed``, ``skipped``,
   ``unsupported`` and ``retryable``. All five advance the bar - a skipped or
   unsupported object is still finished work, and hiding it would strand the
   indicator below 100% forever. ``retryable`` (timeouts, transient connection
   errors) is tracked in its own bucket so the UI can tell "done" from
   "worth another attempt" without losing it from the denominator.
4. ``percent`` is ``terminal / discovered``. It is 0 only when nothing has
   finished, and 100 only when nothing is left outstanding.

Deliberately *not* implemented: a process-wide "current ledger" fallback. With
``JOBS_MAX_CONCURRENT > 1`` a global would silently merge unrelated jobs, so
propagation is explicit and a reader that is not given a ledger accounts into
its own.
"""

from __future__ import annotations

import itertools
import threading
import time
from typing import Any, Callable, Dict, List, Optional

# Terminal outcomes. Anything in this set advances the progress bar.
OUTCOME_COMPLETED = "completed"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_RETRYABLE = "retryable"

TERMINAL_OUTCOMES = (
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_SKIPPED,
    OUTCOME_UNSUPPORTED,
    OUTCOME_RETRYABLE,
)

# Outcomes that mean "this object could succeed if run again".
RETRY_OUTCOMES = (OUTCOME_RETRYABLE,)


class WorkUnit:
    """One unit of processing work, settled exactly once.

    Created by :meth:`ProgressLedger.begin`. Hold on to it and call
    :meth:`settle` on every exit path; the ledger guarantees the counters move
    once no matter how many times (or from how many threads) it is called.
    """

    __slots__ = (
        "ledger", "key", "path", "phase", "depth", "parent",
        "started_at", "ended_at", "outcome", "_settled",
    )

    def __init__(self, ledger: "ProgressLedger", key: int, path: Optional[str],
                 phase: Optional[str], depth: int, parent: Optional[str]):
        self.ledger = ledger
        self.key = key
        self.path = path
        self.phase = phase
        self.depth = depth
        self.parent = parent
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.outcome: Optional[str] = None
        self._settled = False

    @property
    def settled(self) -> bool:
        return self._settled

    def settle(self, outcome: str) -> bool:
        """Close this unit. Returns True for the call that actually counted."""
        return self.ledger.settle(self, outcome)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkUnit {self.path!r} settled={self._settled} outcome={self.outcome!r}>"


class ProgressLedger:
    """Thread-safe, dynamically growing record of processing work."""

    #: Minimum seconds between *time-based* notifications. State-changing
    #: events (discovery, phase change, a new percent) always notify.
    MIN_NOTIFY_INTERVAL = 0.1

    def __init__(self, name: str = "progress",
                 notify: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.name = name
        self._lock = threading.Lock()
        self._counter = itertools.count(1)

        # Discovery
        self.initial_total = 0            # first (top-level) workload
        self.discovered_total = 0         # grows as containers are opened
        self._discovery_keys: Dict[str, int] = {}
        self._initial_locked = False

        # Lifecycle
        self.in_progress = 0
        self._inflight: Dict[int, WorkUnit] = {}
        self._inflight_by_path: Dict[str, WorkUnit] = {}

        # Terminal buckets
        self.counts: Dict[str, int] = {o: 0 for o in TERMINAL_OUTCOMES}

        # Attribution: parent/container -> children discovered from it
        self.children_by_parent: Dict[str, int] = {}
        self.containers_opened = 0

        # Live status
        self.current_file: Optional[str] = None
        self.current_phase: Optional[str] = None
        self.started_at = time.time()

        # Notification
        self.notify = notify
        self._last_notify = 0.0
        self._last_percent = -1

        # High-water mark for the reported percentage (see _percent_locked).
        self._max_percent = 0

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def add_discovered(self, count: int, key: Optional[str] = None,
                       parent: Optional[str] = None, depth: int = 0,
                       initial: bool = False) -> int:
        """Register ``count`` units of work; returns the applied delta.

        ``key`` makes repeated registration of the same container safe: the
        first call records ``count`` against the key, later calls reconcile to
        the new count. Without a key the call is a plain increment.

        ``initial=True`` marks the first, top-level workload so the snapshot can
        report "initial" separately from "total discovered".
        """
        try:
            count = int(count)
        except (TypeError, ValueError):
            return 0
        if count < 0:
            count = 0

        with self._lock:
            if key is not None:
                previous = self._discovery_keys.get(key)
                if previous is None:
                    delta = count
                    self._discovery_keys[key] = count
                else:
                    delta = count - previous
                    self._discovery_keys[key] = count
            else:
                delta = count

            if delta:
                self.discovered_total += delta

            if initial and not self._initial_locked:
                self.initial_total = max(0, self.discovered_total)
                self._initial_locked = True

            if parent is not None and delta > 0:
                self.children_by_parent[parent] = (
                    self.children_by_parent.get(parent, 0) + delta
                )
                self.containers_opened += 1

            percent = self._percent_locked()
            discovered_changed = bool(delta)

        if discovered_changed or percent != self._last_percent:
            self._emit(force=discovered_changed)
        return delta

    def record(self, outcome: str, count: int = 1,
               parent: Optional[str] = None) -> None:
        """Register work that is *already* terminal (skipped / unsupported).

        Adds to the denominator and settles in the same step, so objects that
        never ran still show up in the accounting and cannot strand the bar
        below 100%. Use :meth:`abandon` instead for work that is *already* in
        the denominator.
        """
        if outcome not in TERMINAL_OUTCOMES:
            outcome = OUTCOME_FAILED
        try:
            count = max(0, int(count))
        except (TypeError, ValueError):
            return
        if not count:
            return

        with self._lock:
            self.discovered_total += count
            self.counts[outcome] = self.counts.get(outcome, 0) + count
            if parent is not None:
                self.children_by_parent[parent] = (
                    self.children_by_parent.get(parent, 0) + count
                )
            percent = self._percent_locked()

        if percent != self._last_percent:
            self._emit()

    def abandon(self, count: int, outcome: str = OUTCOME_SKIPPED) -> None:
        """Settle already-discovered work that never entered a worker.

        This is the counterpart to :meth:`record`. ``record`` *adds* to the
        denominator and settles in one step, for work that was never registered
        (a checkpoint skip filtered out before discovery). ``abandon`` only
        settles, for work that IS already in the denominator but will now never
        run - a cancel or pause that cut a submission loop short.

        Using ``record`` here would inflate ``discovered_total`` a second time
        and leave ``pending`` permanently non-zero, which is exactly the
        "indicator can never honestly reach 100%" failure mode.
        """
        if outcome not in TERMINAL_OUTCOMES:
            outcome = OUTCOME_SKIPPED
        try:
            count = max(0, int(count))
        except (TypeError, ValueError):
            return
        if not count:
            return

        with self._lock:
            self.counts[outcome] = self.counts.get(outcome, 0) + count
            percent = self._percent_locked()

        if percent != self._last_percent:
            self._emit()

    # ------------------------------------------------------------------
    # Work lifecycle
    # ------------------------------------------------------------------
    def begin(self, path: Optional[str] = None, phase: Optional[str] = None,
              depth: int = 0, parent: Optional[str] = None) -> WorkUnit:
        """Open a unit of work (increments ``in_progress``)."""
        with self._lock:
            unit = WorkUnit(self, next(self._counter), path, phase, depth, parent)
            self._inflight[unit.key] = unit
            if path:
                # Last writer wins for the path index; settle() only uses it as
                # a lookup hint and always clears its own entry.
                self._inflight_by_path[path] = unit
                self.current_file = path
            if phase:
                self.current_phase = phase
            self.in_progress += 1
        return unit

    def settle(self, unit: Optional[WorkUnit], outcome: str) -> bool:
        """Close ``unit`` exactly once. Returns True for the counting call."""
        if unit is None:
            return False
        if outcome not in TERMINAL_OUTCOMES:
            outcome = OUTCOME_FAILED

        with self._lock:
            if unit._settled:
                return False
            unit._settled = True
            unit.outcome = outcome
            unit.ended_at = time.time()

            self._inflight.pop(unit.key, None)
            if unit.path and self._inflight_by_path.get(unit.path) is unit:
                self._inflight_by_path.pop(unit.path, None)

            self.in_progress = max(0, self.in_progress - 1)
            self.counts[outcome] = self.counts.get(outcome, 0) + 1
            percent = self._percent_locked()

        # A settled unit always changes state, so always emit.
        self._emit(force=(percent != self._last_percent))
        return True

    def settle_path(self, path: Optional[str], outcome: str) -> bool:
        """Settle the in-flight unit for ``path`` (used by timeout handling).

        Returns False when nothing is in flight for that path - e.g. the worker
        already settled it, which is exactly the double-count this avoids.
        """
        if not path:
            return False
        with self._lock:
            unit = self._inflight_by_path.get(path)
        if unit is None:
            return False
        return self.settle(unit, outcome)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def set_phase(self, phase: Optional[str]) -> None:
        if not phase:
            return
        with self._lock:
            if self.current_phase == phase:
                return
            self.current_phase = phase
        self._emit(force=True)

    def set_current(self, path: Optional[str]) -> None:
        if not path:
            return
        with self._lock:
            self.current_file = path

    def attach_notifier(self, notify: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Install the outward callback. Only the ledger's owner should call it."""
        self.notify = notify

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------
    def _percent_locked(self) -> int:
        """Reported percentage: monotonic, and 100 only when genuinely done.

        Two properties matter here, and both follow from the denominator being
        *dynamic*:

        * **Never retreats.** Opening a container mid-run grows
          ``discovered_total``, so ``terminal / total`` can legitimately fall
          (2/6 = 33% becomes 2/8 = 25%). A bar that visibly goes backwards is
          indistinguishable from a broken one, so the reported value is clamped
          to its high-water mark. The counters themselves are never fudged -
          ``files_done``/``total_files`` still show the real 2/8.
        * **Never claims 100% early.** While anything is in flight or queued the
          report is capped at 99%. A parent container is in flight for as long
          as its children are being discovered and processed, so this cap is
          exactly what stops "complete" being reported while newly discovered
          nested objects are still waiting.
        """
        total = self.discovered_total
        if total <= 0:
            return 0
        terminal = sum(self.counts.get(o, 0) for o in TERMINAL_OUTCOMES)
        raw = min(100, max(0, int((terminal / total) * 100)))

        if self.in_progress <= 0 and terminal >= total:
            reported = 100
        else:
            reported = min(99, max(raw, self._max_percent))

        if reported > self._max_percent:
            self._max_percent = reported
        return reported

    @property
    def terminal(self) -> int:
        with self._lock:
            return sum(self.counts.get(o, 0) for o in TERMINAL_OUTCOMES)

    @property
    def pending(self) -> int:
        with self._lock:
            return max(0, self.discovered_total - self.in_progress
                       - sum(self.counts.get(o, 0) for o in TERMINAL_OUTCOMES))

    @property
    def percent(self) -> int:
        with self._lock:
            return self._percent_locked()

    @property
    def is_complete(self) -> bool:
        """True only when every discovered unit has reached a terminal state."""
        with self._lock:
            if self.discovered_total <= 0:
                return False
            terminal = sum(self.counts.get(o, 0) for o in TERMINAL_OUTCOMES)
            return self.in_progress <= 0 and terminal >= self.discovered_total

    def snapshot(self) -> Dict[str, Any]:
        """Consistent point-in-time view for progress consumers."""
        with self._lock:
            counts = dict(self.counts)
            total = self.discovered_total
            initial = self.initial_total
            in_progress = self.in_progress
            percent = self._percent_locked()
            current_file = self.current_file
            current_phase = self.current_phase
            containers = self.containers_opened
            by_parent = dict(self.children_by_parent)

        terminal = sum(counts.get(o, 0) for o in TERMINAL_OUTCOMES)
        nested = max(0, total - initial)
        return {
            # --- backward-compatible keys (consumed by the job system) ---
            "total_files": total,
            "files_done": terminal,
            "files_completed": counts.get(OUTCOME_COMPLETED, 0),
            "files_failed": counts.get(OUTCOME_FAILED, 0),
            "in_progress": in_progress,
            "percent": percent,
            "current_file": current_file,
            "current_phase": current_phase,
            # --- dynamic / nested accounting ---
            "files_initial": initial,
            "files_discovered": total,
            "files_nested": nested,
            "nested_discovered": nested,
            "containers_opened": containers,
            "files_skipped": counts.get(OUTCOME_SKIPPED, 0),
            "files_unsupported": counts.get(OUTCOME_UNSUPPORTED, 0),
            "files_retryable": counts.get(OUTCOME_RETRYABLE, 0),
            "files_pending": max(0, total - in_progress - terminal),
            "terminal": terminal,
            "complete": (in_progress <= 0 and total > 0 and terminal >= total),
            "elapsed_seconds": round(time.time() - self.started_at, 3),
            "children_by_parent": by_parent,
        }

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------
    def _emit(self, force: bool = False) -> None:
        cb = self.notify
        if cb is None:
            return
        now = time.time()
        percent = self.percent
        if not force:
            if percent == self._last_percent and (now - self._last_notify) < self.MIN_NOTIFY_INTERVAL:
                return
        self._last_notify = now
        self._last_percent = percent
        try:
            cb(self.snapshot())
        except Exception:
            # A broken consumer must never break processing.
            import logging
            logging.getLogger(__name__).debug("progress notify failed", exc_info=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        s = self.snapshot()
        return (f"<ProgressLedger {self.name} {s['files_done']}/{s['total_files']} "
                f"({s['percent']}%) nested={s['files_nested']} "
                f"in_progress={s['in_progress']}>")


def _result_layers(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The dict layers a reader result can carry status in.

    Readers are not uniform. The router wraps them as ``{"Content": ...,
    "Metadata": ...}``; inside, ``read_img_fast`` reports through
    ``extraction_info`` while others put ``error`` at the top of the payload,
    and ``retryable`` appears at both levels depending on the reader. Looking
    only at ``Content.error`` therefore misses most real failures and silently
    classifies them as successes.
    """
    layers: List[Dict[str, Any]] = [result]
    for container in (result, result.get("Content")):
        if not isinstance(container, dict):
            continue
        if container is not result:
            layers.append(container)
        info = container.get("extraction_info")
        if isinstance(info, dict):
            layers.append(info)
    return layers


def classify_result(result: Any) -> str:
    """Map a processing result onto a terminal outcome.

    Keeps unsupported objects distinguishable from genuine failures so both are
    represented honestly in the accounting (spec item 4/6), and keeps
    *retryable* distinct from *completed* so a dependency failure is never
    reported as a successful extraction.
    """
    if result is None:
        return OUTCOME_SKIPPED
    if not isinstance(result, dict):
        return OUTCOME_FAILED

    layers = _result_layers(result)

    # A reader that explicitly flags the result retryable has already made the
    # determination (missing OCR engine, missing PIL, missing binary). Trust it
    # rather than re-deriving it from message text.
    for layer in layers:
        if layer.get("retryable") is True:
            return OUTCOME_RETRYABLE

    error = reason = None
    extracted = None
    for layer in layers:
        if error is None and layer.get("error"):
            error = str(layer["error"])
        if reason is None and layer.get("reason"):
            reason = str(layer["reason"])
        if extracted is None and "extracted" in layer:
            extracted = bool(layer["extracted"])

    if error or reason:
        text = f"{error or ''} {reason or ''}".lower()
        if "unsupported file type" in text or "no reader" in text:
            return OUTCOME_UNSUPPORTED
        if "maximum recursion depth" in text:
            return OUTCOME_SKIPPED
        if "ocr_required_engine_unavailable" in text:
            # OCR was *required* and no engine existed, so nothing was
            # extracted. read_pdf documents this exact case as "a retryable
            # dependency failure, not a completed extraction"; accounting must
            # agree with the reader instead of reporting an empty result as a
            # success. When content did survive (a PDF's native text layer),
            # the reader says so and the unit is genuinely complete.
            if extracted is False:
                return OUTCOME_RETRYABLE
            return OUTCOME_COMPLETED
        if ("tesseract" in text and "not installed" in text) or "ocr unavailable" in text:
            # OCR is optional here: the object was still read and stored.
            return OUTCOME_COMPLETED
        if "timeout" in text or "connection" in text:
            return OUTCOME_RETRYABLE
        return OUTCOME_FAILED
    return OUTCOME_COMPLETED
