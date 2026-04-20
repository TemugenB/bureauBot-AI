"""Tests for rag/chunker.py — pure logic."""
from backend.rag.chunker import (
    structured_chunk, _is_heading, _is_list_item, _fallback_split,
)


class TestIsHeading:
    def test_colon_terminated(self):
        assert _is_heading("Required documents:")

    def test_all_caps(self):
        assert _is_heading("PROCEDURE")

    def test_normal_text(self):
        assert not _is_heading("This is a normal sentence about documents.")

    def test_empty(self):
        assert not _is_heading("")
        assert not _is_heading("   ")

    def test_long_caps_rejected(self):
        # More than 10 words in caps — not a heading
        assert not _is_heading("THIS IS A VERY LONG LINE THAT HAS MORE THAN TEN WORDS IN IT")


class TestIsListItem:
    def test_dash(self):
        assert _is_list_item("- item one")

    def test_asterisk(self):
        assert _is_list_item("* item two")

    def test_bullet(self):
        assert _is_list_item("• item three")

    def test_numbered_dot(self):
        assert _is_list_item("1. first step")

    def test_numbered_paren(self):
        assert _is_list_item("2) second step")

    def test_normal_text(self):
        assert not _is_list_item("This is not a list item.")


class TestStructuredChunk:
    def test_splits_by_headings(self):
        text = "Introduction:\nSome intro text.\n\nProcedure:\nStep one.\nStep two."
        chunks = structured_chunk(text, doc_id="d1")
        parents = [c for c in chunks if c.parent_id is None]
        children = [c for c in chunks if c.parent_id is not None]
        assert len(parents) == 2
        assert parents[0].section_title == "Introduction"
        assert parents[1].section_title == "Procedure"
        assert len(children) > 0

    def test_no_headings(self):
        text = "Just a plain paragraph with no headings at all."
        chunks = structured_chunk(text, doc_id="d1")
        parents = [c for c in chunks if c.parent_id is None]
        assert len(parents) >= 1
        assert parents[0].section_title == "Introduction"

    def test_children_reference_parent(self):
        text = "Section:\nParagraph one.\n\nParagraph two."
        chunks = structured_chunk(text, doc_id="d1")
        parents = {c.id: c for c in chunks if c.parent_id is None}
        children = [c for c in chunks if c.parent_id is not None]
        for child in children:
            assert child.parent_id in parents

    def test_empty_sections_skipped(self):
        text = "Header One:\n\nHeader Two:\nActual content here."
        chunks = structured_chunk(text, doc_id="d1")
        parents = [c for c in chunks if c.parent_id is None]
        titles = [p.section_title for p in parents]
        assert "Header One" not in titles
        assert "Header Two" in titles

    def test_list_items_become_children(self):
        text = "Steps:\n- Step one\n- Step two\n- Step three"
        chunks = structured_chunk(text, doc_id="d1")
        list_items = [c for c in chunks if c.chunk_type == "list_item"]
        assert len(list_items) == 3

    def test_doc_id_propagated(self):
        text = "Title:\nContent here."
        chunks = structured_chunk(text, doc_id="my-doc")
        assert all(c.doc_id == "my-doc" for c in chunks)


class TestFallbackSplit:
    def test_respects_chunk_size(self):
        text = " ".join(["word"] * 1500)
        chunks = _fallback_split(text, "d1", "sec", "p1", "parent")
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.content.split()) <= 512 + 10  # small tolerance

    def test_overlap(self):
        text = " ".join([f"w{i}" for i in range(1024)])
        chunks = _fallback_split(text, "d1", "sec", "p1", "parent")
        # With overlap, chunks should share some words
        if len(chunks) >= 2:
            words_0 = set(chunks[0].content.split())
            words_1 = set(chunks[1].content.split())
            assert len(words_0 & words_1) > 0
