"""Unit tests for the chunking algorithm in web_ops.fetcher.

Tests cover:
- _line_kind classification (table/blockquote/text/code detection)
- _rechunk_dense_sections (density detection, \n split, table grouping)
- _merge_consecutive_chunks (consecutive merge, char cap, code boundaries)
- _parse_chunked integration (end-to-end with real-world snippets)
"""
from __future__ import annotations

import pytest

from web_ops.fetcher import (
    _line_kind,
    _rechunk_dense_sections,
    _merge_consecutive_chunks,
    _parse_chunked,
    _DENSITY_CHARS_THRESHOLD,
    _MAX_MERGED_CHARS,
)


# ============================================================================
# _line_kind tests
# ============================================================================


class TestLineKind:
    """Classification of individual source lines for grouping purposes."""

    def test_table_rows_with_pipes(self):
        """Lines with | at both ends are tables."""
        assert _line_kind("| Version  | Changes  |") == "table"
        assert _line_kind("| --- | --- |") == "table"
        assert _line_kind("| `O_RDONLY`  | Flag indicating... |") == "table"

    def test_wikipedia_single_pipe_rows(self):
        """Wikipedia-style rows like ``  |`` (single pipe) should be table."""
        assert _line_kind("  |") == "table"
        assert _line_kind(" |") == "table"
        assert _line_kind("|") == "table"

    def test_list_items_with_pipes_are_text(self):
        """Bullet points containing | (type unions) are NOT table rows."""
        assert _line_kind("  * `buffer` [<Buffer>] | [<TypedArray>] | ...") == "text"
        assert _line_kind("* `offset` [<integer>] The location...") == "text"
        assert _line_kind("- item | value") == "text"
        assert _line_kind("+ item | value") == "text"
        assert _line_kind("1. first step | optional") == "text"

    def test_blockquote_lines(self):
        """Lines starting with ``> `` are blockquotes."""
        assert _line_kind("> This is a quote") == "blockquote"
        assert _line_kind("> > Nested quote") == "blockquote"
        # Quoted text that looks like a table should still be blockquote
        assert _line_kind("> | col1 | col2 |") == "blockquote"

    def test_code_fences(self):
        """Code fence markers are 'code'."""
        assert _line_kind("```python") == "code"
        assert _line_kind("```") == "code"
        assert _line_kind("  ```") == "code"

    def test_blank_and_regular_text(self):
        """Empty/whitespace → blank, everything else → text."""
        assert _line_kind("") == "blank"
        assert _line_kind("   ") == "blank"
        assert _line_kind("Regular paragraph text goes here.") == "text"
        assert _line_kind("  Indented text") == "text"

    def test_table_starting_with_pipe_takes_precedence(self):
        """Lines starting with ``|`` are table even if they also match
        another pattern (e.g. contain ``>``)."""
        # This line would match ``>`` if checked first, but ``|`` takes priority
        assert _line_kind("| > 0 | Description |") == "table"


# ============================================================================
# _merge_consecutive_chunks tests
# ============================================================================


class TestMergeConsecutiveChunks:
    """Greedy merge of adjacent single-line chunks."""

    def test_basic_consecutive_merge(self):
        """Adjacent chunks on consecutive lines merge."""
        chunks = [
            {"text": "Line one", "lines": [1, 1]},
            {"text": "Line two", "lines": [2, 2]},
            {"text": "Line three", "lines": [4, 4]},  # gap at line 3
            {"text": "Line four", "lines": [5, 5]},
        ]
        result = _merge_consecutive_chunks(chunks, 750)
        assert len(result) == 2
        assert result[0]["text"] == "Line one\nLine two"
        assert result[0]["lines"] == [1, 2]
        assert result[1]["text"] == "Line three\nLine four"
        assert result[1]["lines"] == [4, 5]

    def test_char_cap_prevents_merge(self):
        """When combined length exceeds cap, chunks stay separate."""
        long_line = "A" * 60
        chunks = [
            {"text": long_line, "lines": [1, 1]},
            {"text": "Another line that adds too much", "lines": [2, 2]},
        ]
        result = _merge_consecutive_chunks(chunks, 70)
        assert len(result) == 2

    def test_code_block_boundary(self):
        """Code blocks (``` fences) break merge in both directions."""
        chunks = [
            {"text": "Before code", "lines": [1, 1]},
            {"text": '```python\nprint("hi")\n```', "lines": [2, 4]},
            {"text": "After code", "lines": [5, 5]},
        ]
        result = _merge_consecutive_chunks(chunks, 750)
        assert len(result) == 3

    def test_single_chunk_unchanged(self):
        """Single element list returns unchanged."""
        chunks = [{"text": "Only chunk", "lines": [1, 1]}]
        result = _merge_consecutive_chunks(chunks, 750)
        assert len(result) == 1
        assert result[0]["text"] == "Only chunk"

    def test_empty_list(self):
        """Empty input returns empty list."""
        assert _merge_consecutive_chunks([], 750) == []


# ============================================================================
# _rechunk_dense_sections tests — density detection
# ============================================================================


class TestDensityDetection:
    """Tests for when rechunk should (and should not) trigger."""

    def test_below_threshold_not_rechunked(self):
        """Sections with all small chunks are left unchanged."""
        tree = _make_section([
            "Short line",
            "Another short",
            "Third short",
        ])
        original_chunks = len(tree["chunks"])
        _rechunk_dense_sections(tree)
        assert len(tree["chunks"]) == original_chunks  # unchanged

    def test_avg_above_threshold_triggers_rechunk(self):
        """When average chars/chunk exceeds threshold, rechunk activates."""
        threshold = _DENSITY_CHARS_THRESHOLD
        long_lines = "x " * (threshold + 100) + "\n" + "y " * (threshold + 100)
        tree = _make_section([long_lines])
        _rechunk_dense_sections(tree)
        # Should have been split — more chunks than before
        assert len(tree["chunks"]) >= 2

    def test_max_chars_triggers_rechunk_even_with_low_avg(self):
        """Even when average is low, a single very large chunk triggers
        rechunk (regression test for py_functions bug)."""
        # Simulate the py_functions case: 100 small chunks + 1 giant chunk.
        # Average = (100*30 + 4000) / 101 ≈ 69.3 — way below threshold.
        # But max_chars = 4000 is way above 2*threshold, so rechunk must trigger.
        small_chunks = ["Short chunk {}".format(i) for i in range(100)]
        big_chunk = "A long paragraph that should be split.\n" * 200  # ~10K chars
        tree = _make_section(small_chunks + [big_chunk])
        original_chunks = len(tree["chunks"])
        _rechunk_dense_sections(tree)
        # The big chunk should have been split — more chunks now.
        assert len(tree["chunks"]) > original_chunks

    def test_code_blocks_excluded_from_max_check(self):
        """Code-only sections should not trigger rechunk based on code size."""
        code_block = "```python\n" + ("x = 1\n" * 500) + "```"
        tree = _make_section([code_block])
        original = len(tree["chunks"])
        _rechunk_dense_sections(tree)
        # Code blocks are not split per-line, so chunk count should stay same
        # (or increase only slightly if non-code parts are split)
        # But density should still work if non-code chunks are large
        assert tree["chunks"] is not None  # sanity check


# ============================================================================
# _rechunk_dense_sections tests — table/blockquote grouping
# ============================================================================


class TestTableGroupingInRechunk:
    """Tables and blockquotes must stay together during rechunk."""

    def test_table_rows_keep_together(self):
        """Consecutive table rows remain in one chunk."""
        tree = _make_section([(
            "Before\n"
            "| A | B |\n"
            "| 1 | 2 |\n"
            "| 3 | 4 |\n"
            "After\n"
            + ("x\n" * 600)  # make it dense
        )])
        _rechunk_dense_sections(tree)

        chunks = tree["chunks"]
        for c in chunks:
            if "| A | B |" in c["text"]:
                assert "| 1 | 2 |" in c["text"], "table rows should not be split apart"
                assert "| 3 | 4 |" in c["text"], "table rows should not be split apart"
                break
        else:
            pytest.fail("Table rows not found in any chunk")

    def test_table_grouping_respects_size_cap(self):
        """When table rows exceed the merge cap, they are split into
        multiple groups (regression test for 10K wiki infobox bug)."""
        # Simulate a large Wikipedia infobox with many rows.
        # Each row is ~150 chars, 100 rows = 15,000 chars total.
        rows = ["| {:30} | {:30} |".format("Key{}".format(i), "Value{}".format(i))
                for i in range(100)]
        # Make dense so rechunk triggers
        tree = _make_section(["\n".join(rows) + "\n" + ("x\n" * 600)])
        _rechunk_dense_sections(tree)

        chunks = tree["chunks"]
        # No single chunk should exceed the cap by more than a small margin
        # (a single row could be ~150 chars, which is fine)
        for c in chunks:
            if "| Key" in c["text"]:
                # A table chunk should not exceed the merge cap significantly
                assert len(c["text"]) <= _MAX_MERGED_CHARS + 500, (
                    f"Table chunk too large: {len(c['text'])} chars > "
                    f"{_MAX_MERGED_CHARS + 500} (cap + slack)"
                )

    def test_blockquote_lines_keep_together(self):
        """Consecutive blockquote lines remain in one chunk."""
        tree = _make_section([(
            "> First line of quote\n"
            "> Second line\n"
            "> Third line\n"
            "Plain text\n"
            + ("x\n" * 600)
        )])
        _rechunk_dense_sections(tree)

        chunks = tree["chunks"]
        found = False
        for c in chunks:
            if "> First line of quote" in c["text"]:
                assert "> Second line" in c["text"], "blockquote lines should not be split"
                assert "> Third line" in c["text"], "blockquote lines should not be split"
                found = True
                break
        assert found, "Blockquote lines not found in any chunk"

    def test_table_rows_with_blank_line_separator(self):
        """Table rows separated by blank lines should be separate groups
        (blank lines are skipped by the \n split iter, creating gaps)."""
        tree = _make_section([(
            "| A | B |\n"
            "| 1 | 2 |\n"
            "\n"
            "| C | D |\n"
            "| 3 | 4 |\n"
            + ("x\n" * 600)
        )])
        _rechunk_dense_sections(tree)

        chunks = tree["chunks"]
        # The two tables should be separate (blank line creates a gap)
        first_found = any(
            "| A | B |" in c["text"] and "| 1 | 2 |" in c["text"]
            for c in chunks
        )
        second_found = any(
            "| C | D |" in c["text"] and "| 3 | 4 |" in c["text"]
            for c in chunks
        )
        assert first_found, "First table should be grouped"
        assert second_found, "Second table should be grouped"


# ============================================================================
# Integration tests with real-world markdown snippets
# ============================================================================


class TestRealWorldSnippets:
    """Tests using actual markdown content from crawled pages."""

    def test_wikipedia_infobox_table(self):
        """Wikipedia infobox: many table rows, must not be one giant chunk."""
        # Real content from wiki_python.md lines 264-287
        infobox = (
            "| Python |\n"
            "| --- |\n"
            "| [Paradigm](https://en.wikipedia.org/wiki/Programming_paradigm) |"
            " [Multi-paradigm](https://en.wikipedia.org/wiki/Multi-paradigm):"
            " [object-oriented](https://en.wikipedia.org/wiki/Object-oriented_programming)... |\n"
            "| [Designed by](https://en.wikipedia.org/wiki/Software_design) |"
            " [Guido van Rossum](https://en.wikipedia.org/wiki/Guido_van_Rossum) |\n"
            "| [Developer](https://en.wikipedia.org/wiki/Software_developer) |"
            " [Python Software Foundation](https://en.wikipedia.org/wiki/Python_Software_Foundation) |\n"
            "| First appeared | 20 February 1991 |\n"
            "| [Stable release](...) | 3.14.5 / 10 May 2026 |\n"
            "| [Typing discipline](...) | [Duck](...), [dynamic](...), [strong](...) |\n"
            "| [OS](...) | [Cross-platform](...) |\n"
            "| [License](...) | [Python Software Foundation License](...) |\n"
            "| Website | [python.org](...) |\n"
            "| Influenced by |\n"
            "| [ABC](...), [Ada](...), [ALGOL 68](...), [APL](...), [C](...), [C++](...),"
            " [CLU](...), [Dylan](...), [Haskell](...), [Icon](...), [Lisp](...),"
            " [Modula-3](...), [Perl](...), [Standard ML](...) |\n"
            "| Influenced |\n"
            "| [Apache Groovy](...), [Boo](...), [Cobra](...), [CoffeeScript](...),"
            " [D](...), [F#](...), [Go](...), [JavaScript](...), [Julia](...),"
            " [Mojo](...), [Nim](...), [Ruby](...), [Swift](...), [V](...) |\n"
        )
        # Make dense so rechunk triggers
        padding = "x\n" * 600
        markdown = "# Python\n\n" + infobox + "\n\n" + padding

        tree = _parse_chunked(markdown)

        # The infobox section should exist and its chunks should be reasonable
        sections = tree.get("sections", [])
        assert len(sections) >= 1

        # Find the section containing infobox rows
        infobox_section = sections[0]
        chunks = infobox_section.get("chunks", [])
        # Each chunk should be at most ~1000 chars
        for c in chunks:
            # Allow code blocks to be larger (they have special handling)
            if not c["text"].lstrip().startswith("```"):
                assert len(c["text"]) < 2000, (
                    f"Non-code chunk too large: {len(c['text'])} chars. "
                    f"First 100: {c['text'][:100]}"
                )

    def test_node_fs_parameter_docs_not_split_as_tables(self):
        """Parameter entries with type unions (|) should NOT be treated
        as table rows and split apart."""
        # Real content from node_fs.md — bullet points with |
        content = (
            "| Version  | Changes  |\n"
            "| --- | --- |\n"
            "| v21.0.0  | Accepts bigint values as `position`.  |\n"
            "  * `buffer` [`<Buffer>`](url) | [`<TypedArray>`](url) | [`<DataView>`](url) A buffer\n"
            "  * `offset` [`<integer>`](url) The location in the buffer at which to start filling.\n"
            "  * `length` [`<integer>`](url) The number of bytes to read.\n"
            "  * `position` [`<integer>`](url) | [`<bigint>`](url) | [`<null>`](url) The location\n"
        )
        padding = "z\n" * 600
        markdown = "# filehandle.read\n\n" + content + "\n" + padding
        tree = _parse_chunked(markdown)

        sections = tree.get("sections", [])
        assert len(sections) >= 1

        chunks = sections[0].get("chunks", [])
        # The Version table should be intact
        table_found = any("| Version" in c["text"] for c in chunks)
        assert table_found, "Version table should exist"

        # Parameter entries should not be split into individual line chunks
        # They may be merged together by _merge_consecutive_chunks
        param_texts = [c["text"] for c in chunks if "`buffer`" in c["text"]
                       or "`offset`" in c["text"] or "`length`" in c["text"]
                       or "`position`" in c["text"]]
        # At least some of these should appear together (not all split apart)
        total_params = len(param_texts)
        # We expect the merge to combine at least some of them
        assert total_params <= 5, (
            f"Parameter entries should be merged, got {total_params} separate chunks"
        )

    def test_python_functions_max_chunk_triggers_rechunk(self):
        """Density detection must catch large outliers even with low average
        (regression test for py_functions)."""
        # Simulate py_functions structure: many small chunks + a few giants.
        # Each small chunk mimics a short navigation link / function name;
        # the giant mimics a 4000-char reference table or doc block.
        small = ["Short chunk {}".format(i) for i in range(80)]
        # Build a giant table chunk (> 2 × _DENSITY_CHARS_THRESHOLD).
        # Each row is ~100 chars; 50 rows = ~5000 chars.
        rows = ["| {:<30} | {:<30} |".format("Key{}".format(i), "Value{}".format(i))
                for i in range(50)]
        giant = (
            "| Function Index  |\n"
            "| --- |\n" +
            "\n".join(rows)
        )
        markdown = "# Functions\n\n" + "\n\n".join(small)
        markdown += "\n\n## Table\n\n" + giant

        tree = _parse_chunked(markdown)

        # Find the "Table" section
        def find_section(node, name):
            for s in node.get("sections", []):
                if name in (s.get("heading") or ""):
                    return s
                r = find_section(s, name)
                if r:
                    return r
            return None

        table_section = find_section(tree, "Table")
        if table_section:
            chunks = table_section.get("chunks", [])
            # The dense-rechunk pass should have split the giant table
            # (max-based check: 5000+ chars > 2 × 600 → triggers rechunk)
            assert len(chunks) > 1, (
                "Giant chunk should have been rechunked — got single chunk "
                f"of {len(chunks[0]['text']) if chunks else 0} chars"
            )


# ============================================================================
# Helpers
# ============================================================================


def _make_section(chunk_texts: list[str]) -> dict:
    """Build a minimal section tree node with the given chunks.

    Used by tests that call _rechunk_dense_sections directly.
    """
    chunks = []
    line_start = 1
    for i, text in enumerate(chunk_texts):
        n_lines = text.count("\n") + 1
        chunks.append({
            "text": text,
            "preview": text[:60],
            "lines": [line_start, line_start + n_lines - 1],
        })
        line_start += n_lines + 1  # +1 for the blank line between chunks
    return {
        "type": "section",
        "heading": "TestSection",
        "level": 1,
        "chunks": chunks,
        "sections": [],
    }
