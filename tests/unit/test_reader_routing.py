"""Extension-to-reader conflict resolution and CSV structure (ROUTE-01).

Defect: ``FileReaderService._build_extension_map`` resolved extensions claimed
by more than one reader with "first reader wins", where "first" meant position
in the ``_readers`` list. ``.csv`` was claimed by both RemainingFileReader and
OfficeFileReader; RemainingFileReader was registered first, so every CSV was
read as undifferentiated plain text and ``OfficeFileReader.read_csv_file`` -
plus ``StoragePipeline._extract_csv_text``, which is keyed on
``content['rows']`` - were unreachable dead code.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reader_file.readers.read_office import MAX_CSV_ROWS, OfficeFileReader  # noqa: E402
from reader_file.services.file_reader_service import FileReaderService  # noqa: E402
from reader_file.services.file_router_service import FileRouterService  # noqa: E402


@pytest.fixture(scope="module")
def reader_service():
    return FileReaderService()


@pytest.fixture(scope="module")
def router():
    return FileRouterService()


def write_csv(tmp_path, text, name="data.csv"):
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


def process(router, path: Path):
    file_info = {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "type": "FILE",
        "size": path.stat().st_size,
    }
    result = router.process_file(file_info, collect=False, store_result=False)
    return result["Content"]


class TestConflictResolution:
    def test_csv_routes_to_the_structured_reader(self, reader_service):
        """The headline defect: .csv used to reach the plain-text reader."""
        assert isinstance(
            reader_service.get_reader_for_extension(".csv"), OfficeFileReader
        )

    def test_all_known_conflicts_are_resolved_explicitly(self, reader_service):
        claims = {}
        for reader in reader_service._readers:
            for ext in reader.get_supported_extensions():
                claims.setdefault(ext, []).append(reader.__class__.__name__)
        contested = {e: n for e, n in claims.items() if len(n) > 1}
        undeclared = set(contested) - set(FileReaderService.EXTENSION_PREFERENCES)
        assert not undeclared, (
            f"contested extensions with no declared preference: {sorted(undeclared)}"
        )

    @pytest.mark.parametrize(
        "ext,expected",
        [
            (".csv", "OfficeFileReader"),
            (".rtf", "RemainingFileReader"),
            (".ts", "RemainingFileReader"),
            (".webm", "VideoFileReader"),
        ],
    )
    def test_declared_preference_wins(self, reader_service, ext, expected):
        assert type(reader_service.get_reader_for_extension(ext)).__name__ == expected

    def test_every_advertised_extension_still_resolves(self, reader_service):
        """Resolution must not orphan any advertised format."""
        for ext in reader_service.get_supported_extensions():
            assert reader_service.get_reader_for_extension(ext) is not None, ext


class TestCsvStructure:
    def test_csv_yields_headers_and_rows(self, router, tmp_path):
        content = process(
            router,
            write_csv(tmp_path, "region,product,units\nEMEA,Widget,12\nAPAC,Gadget,7\n"),
        )
        assert not content.get("error"), content.get("error")
        assert content["headers"] == ["region", "product", "units"]
        assert content["rows"] == [["EMEA", "Widget", "12"], ["APAC", "Gadget", "7"]]
        assert content["row_count"] == 2
        assert content["column_count"] == 3

    def test_csv_content_is_no_longer_raw_comma_text(self, router, tmp_path):
        """Regression guard against falling back to the plain-text reader."""
        content = process(router, write_csv(tmp_path, "a,b\n1,2\n"))
        assert "rows" in content
        assert "encoding_used" in content
        # The plain-text reader's signature keys must be absent.
        assert "lines" not in content
        assert "non_empty_lines" not in content

    def test_storage_can_turn_csv_into_searchable_text(self, router, tmp_path):
        """The previously dead StoragePipeline CSV path must now be reachable."""
        from pipeline.storage_pipeline import StoragePipeline

        content = process(
            router,
            write_csv(tmp_path, "region,product\nEMEA,Widget\nAPAC,Gadget\n"),
        )

        class _Stub(StoragePipeline):
            def __init__(self):
                pass

        text = _Stub()._extract_text_from_content(content)
        assert "EMEA" in text and "Widget" in text
        assert "region" in text

    def test_csv_values_remain_searchable_end_to_end(self, router, tmp_path):
        content = process(
            router, write_csv(tmp_path, "id,note\n7,MARKER-CSV-4417\n")
        )
        assert any("MARKER-CSV-4417" in cell for row in content["rows"] for cell in row)

    def test_quoted_fields_are_parsed_not_split(self, router, tmp_path):
        content = process(
            router, write_csv(tmp_path, 'name,desc\n"Smith, John","a ""quoted"" value"\n')
        )
        assert content["headers"] == ["name", "desc"]
        assert content["rows"][0][0] == "Smith, John"

    def test_empty_csv_reports_an_explicit_error(self, reader_service, tmp_path):
        target = write_csv(tmp_path, "")
        result = reader_service.get_reader_for_extension(".csv").read_csv_file(str(target))
        assert result.get("error") == "Empty file"

    def test_header_only_csv_has_zero_rows(self, router, tmp_path):
        content = process(router, write_csv(tmp_path, "a,b,c\n"))
        assert not content.get("error"), content.get("error")
        assert content["headers"] == ["a", "b", "c"]
        assert content["row_count"] == 0
        assert content["rows"] == []


class TestCsvRowCap:
    """ROUTE-01 moves large CSVs into a reader that materialises rows."""

    def test_cap_constants_are_sane(self):
        assert MAX_CSV_ROWS > 0
        assert isinstance(MAX_CSV_ROWS, int)

    def test_rows_beyond_the_cap_are_counted_but_not_retained(
        self, reader_service, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("reader_file.readers.read_office.MAX_CSV_ROWS", 10)
        target = tmp_path / "big.csv"
        lines = ["a,b"] + [f"{i},x" for i in range(25)]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = reader_service.get_reader_for_extension(".csv").read_csv_file(str(target))
        assert result["row_count"] == 25, "the true file size must still be reported"
        assert result["rows_stored"] == 10
        assert len(result["rows"]) == 10
        assert result["truncated"] is True
        assert "25" in result["truncation_note"]

    def test_untruncated_file_reports_matching_counts(self, router, tmp_path):
        content = process(router, write_csv(tmp_path, "a,b\n1,2\n3,4\n"))
        assert content["row_count"] == 2
        assert content["rows_stored"] == 2
        assert content["truncated"] is False
        assert "truncation_note" not in content
