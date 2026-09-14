"""Unit tests for StoragePipeline._resolve_processing_status.

The pre-existing model stored only file_status in ('Read','Unread'), which says
whether text exists, not what happened. A corrupt file, a deliberately skipped
icon and an unrecognised type all landed as 'Unread' and were indistinguishable
afterwards. These tests pin the distinction.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.storage_pipeline import StoragePipeline  # noqa: E402


def _resolve(content, file_status="Unread"):
    return StoragePipeline._resolve_processing_status(None, content, file_status)


def test_every_returned_state_is_permitted_by_the_schema():
    """Migration 0007 constrains the column; a typo would be a runtime error."""
    allowed = {
        "discovered", "queued", "processing", "processed", "partially_processed",
        "failed", "unsupported", "skipped", "retrying",
    }
    assert set(StoragePipeline.TERMINAL_PROCESSING_STATES) <= allowed


def test_no_in_flight_states_are_claimed():
    """This is a synchronous write path: it cannot truthfully know these."""
    for state in ("queued", "processing", "retrying"):
        assert state not in StoragePipeline.TERMINAL_PROCESSING_STATES


def test_clean_text_is_processed():
    assert _resolve({"text": "hello"}, "Read") == ("processed", None)


def test_unsupported_type_beats_failed():
    """Order matters: an unsupported type also carries an error string."""
    status, detail = _resolve({"error": "Unsupported file type: .xyz"})
    assert status == "unsupported"
    assert ".xyz" in detail


def test_corrupt_input_is_failed_with_the_real_reason():
    status, detail = _resolve({"error": "Failed to open file 'x.pdf' as type pdf"})
    assert status == "failed"
    assert "Failed to open file" in detail


def test_skipped_carries_its_reason():
    status, detail = _resolve({"extraction_info": {"skipped": True, "skip_reason": "too_small"}})
    assert status == "skipped"
    assert detail == "too_small"


def test_skipped_without_a_reason_is_still_skipped():
    assert _resolve({"extraction_info": {"skipped": True}})[0] == "skipped"


def test_ocr_attempted_without_text_is_partial_not_clean():
    status, detail = _resolve({"ocr_attempted": True, "ocr_successful": False, "text": ""})
    assert status == "partially_processed"
    assert "ocr" in detail


def test_successful_ocr_is_not_partial():
    status, _ = _resolve(
        {"ocr_attempted": True, "ocr_successful": True, "text": "MARKER"}, "Read"
    )
    assert status == "processed"


def test_engine_error_makes_the_result_partial():
    status, detail = _resolve(
        {"text": "some", "extraction_info": {"engine_error": "engine crashed"}}, "Read"
    )
    assert status == "partially_processed"
    assert "engine crashed" in detail


def test_truncated_input_is_partial():
    status, _ = _resolve(
        {"text": "partial", "extraction_info": {"truncated": True}}, "Read"
    )
    assert status == "partially_processed"


def test_some_pages_failed_is_partial():
    pages = [
        {"page_number": 1, "method": "direct_extraction", "text": "a"},
        {"page_number": 2, "method": "ocr_failed", "error": "no engine"},
    ]
    status, detail = _resolve({"pages": pages})
    assert status == "partially_processed"
    assert "1 of 2" in detail


def test_every_page_failing_is_failed_not_partial():
    pages = [
        {"page_number": 1, "error": "corrupt"},
        {"page_number": 2, "method": "conversion_failed"},
    ]
    assert _resolve({"pages": pages})[0] == "failed"


def test_all_pages_direct_extraction_is_processed():
    pages = [{"page_number": 1, "method": "direct_extraction", "text": "a"}]
    assert _resolve({"pages": pages})[0] == "processed"


def test_empty_but_readable_is_processed_not_failed():
    """file_status 'Read' means content exists, so nothing needs qualifying."""
    assert _resolve({"text": "", "file_path": "/x/empty.txt"}, "Read") == ("processed", None)


def test_unread_with_no_text_explains_itself():
    """'Unread' alone cannot say why; status_detail must."""
    assert _resolve({"text": ""}, "Unread") == ("processed", "no extractable text")


def test_no_content_at_all_reports_no_extractable_text():
    assert _resolve({}, "Unread") == ("processed", "no extractable text")


def test_status_detail_is_length_capped():
    status, detail = _resolve({"error": "x" * 5000})
    assert status == "failed"
    assert len(detail) <= 2000


def test_non_dict_content_does_not_raise():
    for bad in (None, 42, "text", []):
        assert _resolve(bad)[0] == "processed"


def test_non_dict_extraction_info_does_not_raise():
    assert _resolve({"extraction_info": "not a dict"})[0] == "processed"
