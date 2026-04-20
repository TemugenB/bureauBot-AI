"""Tests for hallucination/verifier.py — pure logic."""
from backend.hallucination.verifier import CitationVerifier
from backend.rag.fusion import RetrievedChunk


def _chunk(id="c1", content="Official document content here.", doc_id="d1",
           score=0.9, section_title="Procedure", child_content="",
           parent_content=""):
    return RetrievedChunk(id=id, content=content, doc_id=doc_id,
                          score=score, section_title=section_title,
                          child_content=child_content,
                          parent_content=parent_content)


class TestVerify:
    def setup_method(self):
        self.verifier = CitationVerifier()

    def test_extracts_citations(self):
        sources = [_chunk("abc-123")]
        response = "You must bring your passport. [SRC:abc-123]"
        result = self.verifier.verify(response, sources)
        assert len(result.citations) == 1
        assert result.citations[0].chunk_id == "abc-123"
        assert result.citations[0].doc_id == "d1"

    def test_unknown_citation_id(self):
        sources = [_chunk("abc-123")]
        response = "Info here. [SRC:unknown-id]"
        result = self.verifier.verify(response, sources)
        # Unknown ID should not appear in citations
        assert len(result.citations) == 0

    def test_ungrounded_factual_sentence(self):
        sources = [_chunk("c1")]
        response = "You must submit form A within 30 days."
        result = self.verifier.verify(response, sources)
        assert not result.verified
        assert len(result.ungrounded_sentences) > 0

    def test_verified_when_all_cited(self):
        sources = [_chunk("c1")]
        # Citation must be within the same sentence for the verifier to see it
        response = "You must submit form A within 30 days [SRC:c1]."
        result = self.verifier.verify(response, sources)
        assert result.verified

    def test_non_factual_text_passes(self):
        sources = [_chunk("c1")]
        response = "Hello, how can I help you today?"
        result = self.verifier.verify(response, sources)
        assert result.verified

    def test_clean_response_strips_markers(self):
        sources = [_chunk("c1")]
        response = "Bring your passport. [SRC:c1] Also your photo. [SRC:c1]"
        result = self.verifier.verify(response, sources)
        assert "[SRC:" not in result.clean_response
        assert "passport" in result.clean_response


class TestBuildSystemPrompt:
    def test_includes_source_blocks(self):
        chunks = [_chunk("c1", "Content about passports.", section_title="Passports")]
        prompt = CitationVerifier.build_system_prompt(chunks)
        assert "id:c1" in prompt
        assert "section:Passports" in prompt
        assert "Content about passports." in prompt

    def test_includes_child_content_marker(self):
        chunks = [_chunk("c1", "Parent content.", child_content="Child detail.",
                         parent_content="Parent content.")]
        prompt = CitationVerifier.build_system_prompt(chunks)
        assert ">>> MOST RELEVANT SECTION:" in prompt
        assert "Child detail." in prompt

    def test_no_child_marker_when_same(self):
        text = "Same content."
        chunks = [_chunk("c1", text, child_content=text, parent_content=text)]
        prompt = CitationVerifier.build_system_prompt(chunks)
        # ">>> MOST RELEVANT SECTION:" only appears as a source block marker,
        # not in the instruction text. Check for the full prefix.
        assert ">>> MOST RELEVANT SECTION:" not in prompt

    def test_strict_rules_present(self):
        prompt = CitationVerifier.build_system_prompt([_chunk()])
        assert "[SRC:" in prompt
        assert "ONLY" in prompt
