"""Unit: the interface documentation cannot drift from the registry.

The productization map once contained three numbers for the same thing (57,
40 and 41 endpoints) because they were typed by hand at different times. The
fix is not discipline, it is generation: the reference table in
``docs/INTERFACE_REGISTRY.md`` is produced from the registry, and this test
fails when the two disagree.
"""

from __future__ import annotations

import pathlib

import pytest

from core.interfaces.docgen import BEGIN, END, reference_markdown, splice, summary_lines

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOC = PROJECT_ROOT / "docs/INTERFACE_REGISTRY.md"


@pytest.fixture(scope="module")
def document():
    assert DOC.exists(), "the registry document is missing"
    return DOC.read_text()


class TestGeneratedBlock:
    def test_the_document_embeds_a_generated_block(self, document):
        assert BEGIN in document and END in document

    def test_the_block_matches_the_registry(self, document):
        embedded = document.split(BEGIN, 1)[1].split(END, 1)[0].strip()
        assert embedded == reference_markdown().strip(), (
            "docs/INTERFACE_REGISTRY.md is out of date; regenerate it with "
            "python3 -m core.interfaces.docgen docs/INTERFACE_REGISTRY.md")

    def test_regeneration_is_idempotent(self, document):
        assert splice(splice(document)) == splice(document)

    def test_splicing_preserves_the_prose(self, document):
        updated = splice(document)
        assert updated.startswith(document.split(BEGIN, 1)[0])
        assert updated.endswith(document.split(END, 1)[1])

    def test_splicing_refuses_a_document_without_markers(self):
        with pytest.raises(ValueError):
            splice("a document with no generated block")


class TestCountsAreGenerated:
    def test_summary_lines_come_from_the_registry(self):
        from core.interfaces import summary

        lines = "\n".join(summary_lines())
        data = summary()
        assert str(data["interfaces"]) in lines
        assert str(data["endpoints_owned"]) in lines

    def test_every_interface_appears_in_the_reference(self):
        from core.interfaces import REGISTRY

        reference = reference_markdown()
        for interface in REGISTRY:
            assert f"`{interface.interface_id}`" in reference, interface.interface_id

    def test_the_document_states_no_endpoint_count_of_its_own(self, document):
        """Counts outside the generated block must be labelled as past.

        A count that is not generated goes stale, which is how the same thing
        came to be described as 57, 40 and 41 endpoints in one document. A
        *historical* figure is fine as long as the reader is told that is what
        it is.
        """
        import re

        prose = document.split(BEGIN, 1)[0] + document.split(END, 1)[1]
        historical = ("historical", "at the time", "before the registry", "legacy")
        offenders = []
        for sentence in re.split(r"(?<=[.!?])\s+", prose):
            if not re.search(r"\b\d{2,3}\s+(?:page )?endpoints\b", sentence):
                continue
            if not any(word in sentence.lower() for word in historical):
                offenders.append(" ".join(sentence.split()))
        assert offenders == [], (
            "live endpoint counts belong in the generated block; label historical "
            "figures as historical:\n  " + "\n  ".join(offenders))


class TestOtherDocuments:
    """Documents that describe the registry must not restate its numbers."""

    def test_the_productization_map_points_at_the_registry(self):
        text = (PROJECT_ROOT / "docs/PRODUCTIZATION_MAP.md").read_text()
        # It may describe the gap it measured, but it must name the generated
        # sources rather than presenting itself as the source of truth.
        assert "core/interfaces" in text or "INTERFACE_REGISTRY.md" in text
        assert "legacy" in text.lower()

    def test_the_domain_model_exists(self):
        assert (PROJECT_ROOT / "docs/DOMAIN_MODEL.md").exists()
