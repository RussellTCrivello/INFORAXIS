"""Executable evidence for the log-hygiene fixes.

The user's log showed three distinct problems; each is locked in here as a
static assertion that a ``grep`` cannot make reliably (prints inside string
literals, retry branches guarded by conditions, etc.):

1. ``✅ FILE SUCCESSFULLY STORED IN DATABASE`` printed TWICE per file -
   ``logger.info(success_message)`` plus a ``print(success_message)`` twin
   writing the same block to stdout.  Merged stdout/stderr logs showed the
   block twice, and buffered stdout glued mid-line onto the next record
   (``...paths.id = 18INFO:pipeline...``).
2. ``Progress: 2/11INFO:werkzeug...`` - partial-line ``print(..., end='')``
   progress mixed with logging on the same stream.
3. ``ss.xlsx`` failed 3 times with the SAME ``NameError`` because the
   doc_error handler retried every exception until ``retry_count >=
   max_retries``.  Non-retryable errors must fail after a single attempt.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_PIPELINE = PROJECT_ROOT / "pipeline" / "storage_pipeline.py"
INTEGRATED_READER = PROJECT_ROOT / "pipeline" / "integrated_reader.py"
TIME_UTILS = PROJECT_ROOT / "core" / "time_utils.py"
WEB_APP = PROJECT_ROOT / "apps" / "web" / "app.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# ---------------------------------------------------------------------------
# 1. Duplicate success block
# ---------------------------------------------------------------------------

def test_success_block_has_no_print_twin():
    """logger.info(success_message) must be the ONLY output of the block."""
    tree = parse(STORAGE_PIPELINE)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node) != "print":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == "success_message":
                offenders.append(node.lineno)
    assert offenders == [], (
        f"print(success_message) still present at line(s) {offenders}: the "
        "success block would appear twice in merged logs"
    )


# ---------------------------------------------------------------------------
# 2. Partial-line progress prints
# ---------------------------------------------------------------------------

def _print_calls_with_carriage_return(tree: ast.Module) -> list[int]:
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node) != "print":
            continue
        chunks = []
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            chunks.append(node.args[0].value)
        if node.args and isinstance(node.args[0], ast.JoinedStr):
            for part in node.args[0].values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    chunks.append(part.value)
        if any("\r" in chunk for chunk in chunks):
            offenders.append(node.lineno)
    return offenders


def test_integrated_reader_has_no_partial_line_progress_prints():
    offenders = _print_calls_with_carriage_return(parse(INTEGRATED_READER))
    assert offenders == [], (
        f"carriage-return print() at line(s) {offenders} in integrated_reader: "
        "partial stdout lines glue log records onto themselves"
    )


def test_progress_updates_go_through_the_logger():
    source = INTEGRATED_READER.read_text(encoding="utf-8")
    assert "def _report_progress(" in source
    assert source.count("_report_progress(f\"Progress:") == 7


# ---------------------------------------------------------------------------
# 3. Retry gating for storage failures
# ---------------------------------------------------------------------------

def _find_doc_error_handler(tree: ast.Module) -> ast.ExceptHandler:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.name == "doc_error":
            return node
    raise AssertionError("except handler for doc_error not found in storage_pipeline")


def test_doc_error_retry_is_gated_on_is_retryable_error():
    handler = _find_doc_error_handler(parse(STORAGE_PIPELINE))
    calls = {
        call_name(n)
        for n in ast.walk(handler)
        if isinstance(n, ast.Call)
    }
    assert "is_retryable_error" in calls, (
        "the doc_error handler must gate retries on is_retryable_error; "
        "without it deterministic defects (e.g. NameError) burn every retry "
        "attempt and print a full traceback per attempt"
    )
    # The unconditional 'else: retry anyway' tail must be gone: after the
    # retry branches the handler must fail (files_failed + return).
    handler_source = ast.get_source_segment(
        STORAGE_PIPELINE.read_text(encoding="utf-8"), handler
    )
    assert "Continue to retry" not in handler_source, (
        "unconditional retry tail still present in doc_error handler"
    )


# ---------------------------------------------------------------------------
# 4. Time-utils block print + web logging config
# ---------------------------------------------------------------------------

def test_print_execution_time_emits_one_atomic_block():
    tree = parse(TIME_UTILS)
    func = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "print_execution_time"
    )
    print_calls = [
        n for n in ast.walk(func)
        if isinstance(n, ast.Call) and call_name(n) == "print"
    ]
    assert len(print_calls) == 1, (
        "print_execution_time must print its whole block in ONE call so log "
        "records cannot land between the lines"
    )
    # ANSI colour must be gated on an interactive terminal
    source = TIME_UTILS.read_text(encoding="utf-8")
    assert "sys.stdout.isatty()" in source


def test_web_logging_config_silences_werkzeug_and_line_buffers_stdout():
    source = WEB_APP.read_text(encoding="utf-8")
    assert 'logging.getLogger("werkzeug").setLevel(logging.WARNING)' in source
    assert "sys.stdout.reconfigure(line_buffering=True)" in source
