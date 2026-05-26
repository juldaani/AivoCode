"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, error,
  structured links, ToC entries, and truncation metadata.
- fetch_url(): async function that fetches a URL via CloakBrowser + Crawl4AI
  with caching, truncation, ToC generation, and section extraction.

Why this exists
- Single entry point for web fetching — used by CLI, Python agents, and
  future transport layers without modification.
- Content-aware: large pages (> 10 000 chars) are automatically truncated to a
  table of contents with section previews, preventing agents from pulling
  huge pages into context.  Full content is cached on disk for section-level
  retrieval on demand (also capped at 10 000 chars).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from cloakbrowser import launch_async

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_WAIT_UNTIL_CHOICES: tuple[str, ...] = ("domcontentloaded", "load", "networkidle")
_WaitUntil = Literal["domcontentloaded", "load", "networkidle"]


@dataclass
class FetchResult:
    """Result of a ``fetch_url()`` call.

    Fields:
        markdown: Page body as markdown.  When content exceeds the truncation
            threshold, this contains a human-readable message explaining that
            the full content was saved and a table of contents follows.
            On failure, empty string.
        success: ``True`` if the crawl completed and content was extracted.
        status_code: HTTP status.  ``None`` if the server was never reached.
        error: Error label.  ``None`` on success.
        navigation: Structured navigation links (internal/external).  Populated
            only when ``include_navigation=True`` is passed to ``fetch_url()``.
            ``None`` otherwise.
        toc: Compact table of contents (ordered array of chunk triples and
            ``{"Heading": [...]}`` section objects) when content is truncated.
            ``None`` when content fits under the threshold or a specific
            section was requested via ``heading`` / ``line_range``.
        chunked: Full verbose chunked tree (with ``text``, ``preview``,
            ``lines``) when content is truncated.  ``None`` otherwise.
            Available for programmatic consumers; the ``toc`` field carries
            the agent-facing compact projection.
        total_chars: Total character count of the full original content.
            ``0`` on failure or when a section was extracted.
    """

    markdown: str = ""
    success: bool = False
    status_code: int | None = None
    error: str | None = field(default=None, compare=False)
    navigation: dict[str, list[dict[str, Any]]] | None = None
    toc: list[Any] | None = None
    chunked: dict[str, Any] | None = None
    info: str | None = None
    total_chars: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CDP_PORT: int = 9243
_PAGE_TIMEOUT_MS: int = 10_000
# Extra delay (seconds) after wait conditions are satisfied before capturing.
# Kept at zero because ``load`` already guarantees scripts are executed;
# frameworks that fetch data after hydration (SPAs with API calls) should
# use ``--js-render`` (networkidle) instead.
_DELAY_BEFORE_RETURN_HTML_S: float = 0.0
_DEFAULT_WAIT_UNTIL: _WaitUntil = "load"
# Character threshold above which content is truncated and replaced with a
# table of contents.  Full content is always saved to cache for later retrieval.
_TRUNCATION_THRESHOLD: int = 10_000

# Maximum number of text-chunk previews to include per section/node in the
# compact ToC delivered to agents.  Excess chunks are replaced by a sentinel
# entry with a line range covering all skipped chunks and a message telling
# the agent how to expand that section.
_TOC_MAX_CHUNKS_PER_SECTION: int = 15

# Minimum character count a chunk must have (after URL stripping) to be
# included in the compact ToC.  Chunks below this are typically pure
# boilerplate (e.g. a single bare URL).  Code blocks are excluded from
# this filter.
_MIN_CHUNK_PREVIEW_CHARS: int = 15

# Average characters-per-chunk threshold above which a section is considered
# "dense" — i.e. the \n\n-based parser produced overly-large chunks — and a
# finer \n-based re-split + consecutive-merge pass is applied.
_DENSITY_CHARS_THRESHOLD: int = 600

# Maximum combined text length for two chunks that are merged together when
# they sit on consecutive source lines (no blank-line gap).  Prevents runaway
# merges on truly dense pages while keeping related paragraphs grouped.
_MAX_MERGED_CHARS: int = 750

# Maximum consecutive table rows to keep in one chunk during \n re-split.
# Tables split on \n produce one chunk per row; this cap floors groups of
# rows into predictable-size chunks (e.g. 20 rows ≈ 500-800 chars each)
# instead of char-count-based grouping which varies unpredictably.
_MAX_TABLE_ROWS_PER_CHUNK: int = 20

# Minimum average chars per text-chunk line (after \n split) for the merge
# pass to be skipped.  When individual lines exceed this threshold they are
# self-contained paragraphs (e.g. 400–600‑char prose lines in dense API
# docs) and merging them would fuse unrelated paragraphs together.
# Feed‑page / link‑directory lines are typically < 200 chars and DO benefit
# from grouping — the merge threshold stays in effect for those.
_DENSE_LINE_CHARS_THRESHOLD: int = 300

# Directory where fetched page content is cached on disk.
# Relative to the workspace root.
_CACHE_DIR: Path = Path("tmp/aivocode/cache")

# Cache TTL in seconds.  After this period the cache is considered stale and
# a fresh fetch is triggered automatically.  News sites update frequently;
# 15 min balances freshness against repeated browser launches.
_CACHE_TTL_S: float = 900

# Maximum number of cached files.  When exceeded, the oldest files (by
# modification time) are evicted to keep the cache within bounds.
_CACHE_MAX_FILES: int = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk_preview(text: str, n: int = 60) -> str:
    """First *n* chars of *text*, URLs stripped, leading whitespace removed,
    hard-cut.

    Strips markdown link syntax and bare URLs so the preview (used in both
    the cached chunked tree and the compact ToC) carries real information
    rather than URL cruft.
    """
    return _strip_urls(text)[:n]


# ---------------------------------------------------------------------------
# Markdown chunked-tree parser
# ---------------------------------------------------------------------------


def _parse_chunked(markdown: str) -> dict[str, Any]:
    """Parse raw markdown into a nested chunked tree.

    Builds a recursive tree from ATX headings (``#``..``######``), treating
    content between them as text chunks.  Code fences (`` ``` `` at line
    start) are recognised so that blank lines inside code blocks do **not**
    split chunks.  Outside code blocks, **any run of one or more blank
    lines** (i.e. ``\\n{2,}`` in the raw text) acts as a chunk boundary.
    Horizontal rules (``---``, ``***``, ``___``) are also boundaries.

    After the initial pass, ``_rechunk_dense_sections`` runs as a
    post-process to detect sections where the \n\n-based parser produced
    overly-large chunks and re-split them on ``\\n`` followed by a
    consecutive-merge pass.

    Returns a verbose tree ready for caching — not the compact ToC format
    (see ``_chunked_to_toc`` for that projection).

    Args:
        markdown: Raw markdown string (as produced by Crawl4AI).

    Returns:
        A ``dict`` with keys ``type``, ``heading``, ``level``, ``chunks``
        (list of ``{text, preview, lines}`` dicts), and ``sections``
        (recursive list of the same shape).  The root node has
        ``type="root"`` / ``heading=None`` / ``level=0``.
    """
    lines = markdown.splitlines()
    _HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")

    # Root node — level 0, no heading.
    root: dict[str, Any] = {
        "type": "root",
        "heading": None,
        "level": 0,
        "chunks": [],
        "sections": [],
    }
    # Stack of parent nodes (root is always at index 0).
    stack: list[dict[str, Any]] = [root]

    # Bookkeeping for the chunk currently being accumulated.
    chunk_lines: list[str] = []
    chunk_start: int = -1  # 1‑based line number of first content line

    in_code = False
    total_lines = len(lines)

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1  # 1‑based

        # ── Code-fence toggle ──────────────────────────────────────────
        if re.match(r"^\s*```", raw_line):
            if not in_code:
                # Entering code block — flush pending text chunk first.
                if chunk_lines:
                    _emit_chunk(
                        stack[-1], chunk_lines, chunk_start, line_num - 1,
                    )
                    chunk_lines = []
                    chunk_start = -1
                in_code = True
                chunk_lines = [raw_line]
                chunk_start = line_num
            else:
                # Exiting code block — include closing fence, then emit.
                chunk_lines.append(raw_line)
                _emit_chunk(
                    stack[-1], chunk_lines, chunk_start, line_num,
                )
                chunk_lines = []
                chunk_start = -1
                in_code = False
            continue

        # ── Inside a code block — everything is content ────────────────
        if in_code:
            chunk_lines.append(raw_line)
            continue

        # ── Outside code blocks ────────────────────────────────────────
        stripped = raw_line.strip()

        # ── ATX heading ────────────────────────────────────────────────
        heading_match = re.match(r"^(#{1,6})\s+(.+)", raw_line)
        if heading_match:
            if chunk_lines:
                _emit_chunk(
                    stack[-1], chunk_lines, chunk_start, line_num - 1,
                )
                chunk_lines = []
                chunk_start = -1

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # Pop stack to find the parent whose level < this heading's level,
            # then append a new child section.
            while stack[-1]["level"] >= level:
                stack.pop()

            new_sec: dict[str, Any] = {
                "type": "section",
                "heading": heading_text,
                "level": level,
                "chunks": [],
                "sections": [],
            }
            stack[-1]["sections"].append(new_sec)
            stack.append(new_sec)
            continue

        # ── Horizontal rule (acts like a chunk boundary) ────────────────
        if _HR_RE.match(stripped):
            if chunk_lines:
                _emit_chunk(
                    stack[-1], chunk_lines, chunk_start, line_num - 1,
                )
                chunk_lines = []
                chunk_start = -1
            # The rule line itself is skipped (no content value).
            continue

        # ── Blank line(s) — any run of ≥1 blank lines is a chunk boundary.
        # Even \n\n\n (2+ blank lines) only emits once; subsequent blanks
        # are no-ops because chunk_lines is already flushed.
        if not stripped:
            if chunk_lines:
                _emit_chunk(
                    stack[-1], chunk_lines, chunk_start, line_num - 1,
                )
                chunk_lines = []
                chunk_start = -1
            continue

        # ── Regular content line ───────────────────────────────────────
        if not chunk_lines:
            chunk_start = line_num
        chunk_lines.append(raw_line)

    # Flush trailing chunk (or dangling code block with no closing fence).
    if chunk_lines:
        _emit_chunk(
            stack[-1], chunk_lines, chunk_start, total_lines,
        )

    # Post-process: detect dense sections (where \n\n split produced
    # overly-large chunks) and re-split + merge for finer granularity.
    _rechunk_dense_sections(root)

    return root


def _line_kind(raw_line: str) -> str:
    """Classify a source line for grouping purposes during ``\\n`` splitting.

    Returns one of ``"table"``, ``"blockquote"``, ``"code"``, ``"list"``,
    ``"text"``, or ``"blank"``.

    Heuristic (checked in order):

    1.  **Blank** — empty after trimming.
    2.  **Code** — starts with `` ``` `` (code fence).
    3.  **Blockquote** — starts with ``> `` after trimming.  Checked
        before table so that quoted table rows (``> | col | val |``) stay
        grouped with their surrounding blockquote lines.
    4.  **Table** — starts with ``|`` after trimming.  Catches
        Wikipedia-style single-pipe infobox rows (``  |`` → ``"|"`` → 1
        pipe → would be missed by the count‑based check).
    5.  **List** — starts with ``*``, ``-``, ``+`` (with trailing space)
        or ``N.`` (numbered list).  These are routed through
        indentation‑aware grouping during ``\\n``‑split to keep parent‑
        and‑child items together.
    6.  **Table (count‑based)** — two or more ``|`` characters.
    7.  **Text** — everything else.
    """
    s = raw_line.strip()
    if not s:
        return "blank"
    if s.startswith("```"):
        return "code"
    # Blockquote: check before table so quoted content stays grouped together.
    if s.startswith("> "):
        return "blockquote"
    # Table: lines that start with a pipe — covers single-pipe Wikipedia
    # infobox rows like "  |" that would otherwise be missed.
    if s.startswith("|"):
        return "table"
    # List items: bullet (*/-/+) or numbered (N.).  Checked before the
    # count‑based table check so that parameter docs with type‑union pipes
    # (``* \\`buf\\` | [A] | [B]``) are NOT misclassified as tables.
    if _RE_LIST_ITEM.match(s):
        return "list"
    # Count-based table detection: two or more pipe characters.
    if s.count("|") >= 2:
        return "table"
    return "text"


# Module-level regex for detecting markdown list items (bullet / numbered).
# Bullet markers (*/-/+) require trailing whitespace to distinguish from
# bold/italic (*text*) and horizontal-rule-like lines (---).
# Numbered lists (1., 42.) match any digit + dot at line start.
_RE_LIST_ITEM = re.compile(r"^[\*\-+]\s|\d+\.")

# Module-level regex for detecting blank-line runs (2+ consecutive newlines).
# Used by _is_feed_page to count paragraph-break gaps, not individual \n\n pairs.
_RE_BLANK_LINE_RUN = re.compile(r"\n{2,}")


def _count_leading_spaces(raw_line: str) -> int:
    """Return the indentation width of *raw_line* in space-equivalents.

    Tabs are expanded to 4 spaces to match common browser rendering.
    Only leading whitespace is counted; the method ignores any content
    after the first non-whitespace character.
    """
    count = 0
    for ch in raw_line:
        if ch == " ":
            count += 1
        elif ch == "\t":
            count += 4
        else:
            break
    return count


def _rechunk_dense_sections(tree: dict[str, Any]) -> None:
    """Post-process: detect sections with overly-large chunks and re-split.

    The main ``_parse_chunked`` pass splits on ``\\n{2,}`` (blank lines),
    which works well for most pages.  When a section's chunks are too large
    — detected via **either** a high average per-chunk size **or** a single
    outlier that massively exceeds the threshold — we split every multi-line
    non‑code chunk on ``\\n`` and then merge consecutive single-line chunks
    back into logical groups (up to ``_MAX_MERGED_CHARS`` per group).

    Applied **in-place** to every node in *tree*, depth-first.
    """
    # Process sub-sections first (depth-first).
    for sub in tree.get("sections", []):
        _rechunk_dense_sections(sub)

    chunks: list[dict[str, Any]] = tree.get("chunks", [])
    if not chunks:
        return

    # ── Density check ─────────────────────────────────────────────────
    # Two triggers (either is sufficient):
    #   A. Average chars per chunk exceeds the threshold.
    #   B. The largest chunk exceeds 2× the threshold — catches outliers
    #      where many small chunks mask a few giant ones (e.g. Python
    #      stdlib reference pages with a mix of navigation links and
    #      4 000‑char parameter‑documentation blocks).
    char_counts = [len(c["text"]) for c in chunks]
    total_chars = sum(char_counts)
    avg_chars = total_chars / len(chunks)
    max_chars = max(char_counts)
    if avg_chars <= _DENSITY_CHARS_THRESHOLD and max_chars <= _DENSITY_CHARS_THRESHOLD * 2:
        return  # Well-chunked — leave as-is.

    # ── \n split: break multi-line non-code chunks into per-line chunks.
    # Tables (|...| rows) and blockquotes (> lines) are kept together as
    # single groups with a size cap — splitting them into individual
    # rows/quotes destroys their meaning, but an unbounded group (e.g. a
    # 10 000‑char Wikipedia infobox) is equally useless to an agent.
    # Everything else is split on \n and later re-merged via
    # _merge_consecutive_chunks.
    new_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        text: str = chunk["text"]

        # Keep single-line chunks and code blocks intact.
        if "\n" not in text or text.lstrip().startswith("```"):
            new_chunks.append(chunk)
            continue

        sub_lines = text.split("\n")
        line_start = chunk["lines"][0]

        i = 0
        while i < len(sub_lines):
            stripped = sub_lines[i].strip()
            if not stripped:
                i += 1
                continue

            typ = _line_kind(sub_lines[i])

            if typ in ("table", "blockquote"):
                # Collect consecutive same-type lines, flushing groups
                # when they hit the size limit — tables use row count
                # (predictable, consistent chunk sizes), blockquotes use
                # character count (no concept of "rows").
                j = i
                group_lines: list[str] = []
                group_chars = 0
                while j < len(sub_lines) and _line_kind(sub_lines[j]) == typ:
                    line_text = sub_lines[j].strip()
                    if not line_text:
                        j += 1
                        continue
                    # Decide whether to flush before adding this line.
                    if typ == "table":
                        should_flush = (
                            group_lines
                            and len(group_lines) >= _MAX_TABLE_ROWS_PER_CHUNK
                        )
                    else:  # blockquote
                        should_flush = (
                            group_lines
                            and group_chars + len(line_text) + 1 > _MAX_MERGED_CHARS
                        )
                    if should_flush:
                        # Flush current group, start a new one.
                        group_text = "\n".join(group_lines)
                        new_chunks.append({
                            "text": group_text,
                            "preview": _chunk_preview(group_text),
                            "lines": [line_start + i, line_start + j - 1],
                        })
                        i = j  # next group starts at this index
                        group_lines = []
                        group_chars = 0
                    group_lines.append(line_text)
                    group_chars += len(line_text) + (1 if group_lines else 0)
                    j += 1
                # Emit the final (or only) group.
                if group_lines:
                    group_text = "\n".join(group_lines)
                    new_chunks.append({
                        "text": group_text,
                        "preview": _chunk_preview(group_text),
                        "lines": [line_start + i, line_start + j - 1],
                    })
                i = j
            elif typ == "list":
                # Collect all consecutive list lines first, then split into
                # "subtree" units (top-level item + its children).  Greedy
                # merge of subtrees by total item count — same pattern as
                # the char‑based merge for paragraphs, but counting items
                # instead of characters.
                j = i
                raw_lines: list[str] = []
                while j < len(sub_lines) and _line_kind(sub_lines[j]) == "list":
                    raw_lines.append(sub_lines[j])
                    j += 1

                # Slurp continuation lines — indented text that follows a
                # list item but has no bullet marker (e.g. a wrapped
                # paragraph inside a list item).  Without this, the
                # continuation becomes a solo text chunk, breaking the
                # semantic grouping.
                while j < len(sub_lines):
                    tail = sub_lines[j]
                    if not tail.strip() or tail.strip().startswith("```"):
                        break  # blank line or code fence → end of list
                    if _count_leading_spaces(tail) > 0:
                        raw_lines.append(tail)
                        j += 1
                    else:
                        break  # un-indented line → new content, stop

                # ── Phase 1: split into subtree units ──────────────────
                subtrees: list[list[str]] = []
                current: list[str] = []
                base_indent: int | None = None

                for line in raw_lines:
                    indent = _count_leading_spaces(line)
                    if base_indent is None:
                        base_indent = indent
                        current = [line]
                    elif indent <= base_indent + 1:
                        # New top-level — flush previous subtree.
                        if current:
                            subtrees.append(current)
                        current = [line]
                    else:
                        # Child — stay in current subtree.
                        current.append(line)

                if current:
                    subtrees.append(current)

                # ── Phase 2: greedy merge with item-count cap ─────────
                group_lines: list[str] = []
                group_items: int = 0
                emitted = 0

                for subtree in subtrees:
                    n_items = len(subtree)
                    if group_lines and group_items + n_items > _MAX_TABLE_ROWS_PER_CHUNK:
                        # Would exceed cap — flush current group first.
                        group_text = "\n".join(group_lines)
                        new_chunks.append({
                            "text": group_text,
                            "preview": _chunk_preview(group_text),
                            "lines": [
                                line_start + i + emitted,
                                line_start + i + emitted + len(group_lines) - 1,
                            ],
                        })
                        emitted += len(group_lines)
                        group_lines = []
                        group_items = 0

                    group_lines.extend(subtree)
                    group_items += n_items

                # Emit final group.
                if group_lines:
                    group_text = "\n".join(group_lines)
                    new_chunks.append({
                        "text": group_text,
                        "preview": _chunk_preview(group_text),
                        "lines": [
                            line_start + i + emitted,
                            line_start + i + emitted + len(group_lines) - 1,
                        ],
                    })

                i = j
            else:
                # Single-line chunk (may be merged with neighbours later).
                new_chunks.append({
                    "text": stripped,
                    "preview": _chunk_preview(stripped),
                    "lines": [line_start + i, line_start + i],
                })
                i += 1

    # ── Merge consecutive single-line chunks into logical groups ──────
    # Skip merging when lines are already paragraph-sized — dense prose
    # (e.g. CLI docs, API references) with 400‑600‑char \n‑delimited
    # paragraphs.  Merging would fuse unrelated paragraphs together.
    # Feed pages with 50‑150‑char lines still get the normal merge pass.
    text_chars = [
        len(c["text"]) for c in new_chunks
        if not c["text"].lstrip().startswith("```")
        and c["text"].count("\n") == 0  # single-line text chunks only
    ]
    if text_chars:
        avg_line = sum(text_chars) / len(text_chars)
        if avg_line > _DENSE_LINE_CHARS_THRESHOLD:
            # Dense prose — each line is a paragraph, don't merge.
            tree["chunks"] = new_chunks
            return

    tree["chunks"] = _merge_consecutive_chunks(new_chunks, _MAX_MERGED_CHARS)


def _merge_consecutive_chunks(
    chunks: list[dict[str, Any]],
    max_chars: int,
) -> list[dict[str, Any]]:
    """Greedily merge adjacent chunks that sit on consecutive source lines.

    Two chunks merge when ALL of these hold:
    - They are on consecutive source lines (``chunk_a.end + 1 == chunk_b.start``).
    - Neither is a code block (text starts with `` ``` ``).
    - Neither is a pre-formed multi-line group (tables, blockquotes, lists
      are already grouped inside ``_rechunk_dense_sections`` and should not
      be re-merged with adjacent text).
    - The combined text length stays at or below *max_chars*.

    Merged chunks are joined with ``\\n`` and the line range spans both.
    The preview is recomputed from the merged text via ``_chunk_preview``.
    """
    if not chunks:
        return []

    merged: list[dict[str, Any]] = []
    cur_text = chunks[0]["text"]
    cur_start = chunks[0]["lines"][0]
    cur_end = chunks[0]["lines"][1]
    cur_is_code = cur_text.lstrip().startswith("```")
    cur_is_group = "\n" in cur_text  # table / blockquote / list group

    for i in range(1, len(chunks)):
        nxt = chunks[i]
        nxt_text = nxt["text"]
        nxt_is_code = nxt_text.lstrip().startswith("```")
        nxt_is_group = "\n" in nxt_text
        consecutive = cur_end + 1 == nxt["lines"][0]
        combined_len = len(cur_text) + 1 + len(nxt_text)  # +1 for the joining \n

        if (
            consecutive
            and not cur_is_code
            and not nxt_is_code
            and not cur_is_group
            and not nxt_is_group
            and combined_len <= max_chars
        ):
            # Merge this chunk into the accumulator.
            cur_text += "\n" + nxt_text
            cur_end = nxt["lines"][1]
        else:
            # Emit the accumulated chunk and start fresh with nxt.
            merged.append({
                "text": cur_text,
                "preview": _chunk_preview(cur_text),
                "lines": [cur_start, cur_end],
            })
            cur_text = nxt_text
            cur_start = nxt["lines"][0]
            cur_end = nxt["lines"][1]
            cur_is_code = nxt_is_code
            cur_is_group = nxt_is_group

    # Emit the trailing accumulated chunk.
    merged.append({
        "text": cur_text,
        "preview": _chunk_preview(cur_text),
        "lines": [cur_start, cur_end],
    })

    return merged


def _emit_chunk(
    parent: dict[str, Any],
    lines: list[str],
    start: int,
    end: int,
) -> None:
    """Build a chunk dict from accumulated lines and append to *parent*."""
    text = "\n".join(lines).rstrip()
    if not text:
        return  # Purely blank chunks (shouldn't happen, but safe).
    parent["chunks"].append({
        "text": text,
        "preview": _chunk_preview(text),
        "lines": [start, end],
    })


# ---------------------------------------------------------------------------
# ToC projection (compact, agent-facing)
# ---------------------------------------------------------------------------


def _strip_urls(text: str) -> str:
    """Remove URLs from *text*, keeping link/image alt-text only.

    Strips markdown ``[text](url)``, ``![alt](url)``, bare ``https?://``
    URLs, and orphaned ``](url)`` fragments.  Applied to heading keys and
    chunk previews in the compact ToC to keep the information density high.
    """
    # Markdown images: ![alt](url) → alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Markdown links: [text](url) → text
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Bare URLs
    text = re.sub(r"https?://\S+", "", text)
    # Orphaned closing-link fragments
    text = re.sub(r"\]\([^)]+\)", "", text)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def _chunked_to_toc(tree: dict[str, Any]) -> list[Any]:
    """Project the verbose cached chunked tree into a compact ToC.

    The compact format is an ordered array where:
    - ``[line_start, line_end, "preview"]`` triples are text chunks.
    - ``{"Heading Name": [...]}`` objects are subsections.

    Duplicate heading names at the same level get a ``" (N)"`` suffix.
    The root ``type`` / ``level`` keys and full ``text`` values are
    dropped — only previews and line ranges are retained.
    """
    return _section_to_toc(tree)


def _section_to_toc(node: dict[str, Any]) -> list[Any]:
    """Recursively convert a single node to ToC array entries.

    Caps text-chunk previews at ``_TOC_MAX_CHUNKS_PER_SECTION`` per node
    to prevent context bloat on pages with many short paragraphs (e.g.
    GitHub commit histories).  Skipped chunks are summarised by a sentinel
    triple whose line range spans all of them.
    """
    result: list[Any] = []
    chunks: list[dict[str, Any]] = node.get("chunks", [])

    # Emit up to N chunk previews — cap with sentinel if there are more.
    # Skip trivially-short non-code chunks whose content was mostly URLs.
    # Track *emitted* separately from loop index so that short-filtered
    # chunks don't prematurely exhaust the cap (leaving zero visible
    # previews followed by a sentinel).
    emitted = 0
    i = -1
    for i, chunk in enumerate(chunks):
        text = chunk["text"].strip()
        if not text.startswith("```"):
            if len(_strip_urls(chunk["text"])) < _MIN_CHUNK_PREVIEW_CHARS:
                continue

        ls, le = chunk["lines"]
        result.append([ls, le, chunk["preview"]])
        emitted += 1

        if emitted >= _TOC_MAX_CHUNKS_PER_SECTION:
            break

    # Only add sentinel when we stopped early due to the cap — i.e. there
    # are chunks remaining after the last one we examined.
    if emitted >= _TOC_MAX_CHUNKS_PER_SECTION and i + 1 < len(chunks):
        skipped = len(chunks) - (i + 1)
        first = chunks[i + 1]["lines"][0]
        last = chunks[-1]["lines"][1]
        msg = (
            f"… {skipped} more chunks — use --heading to expand all, "
            f"or --line-range to read selectively"
        )
        result.append([first, last, msg])

    # Subsections — deduplicate heading names within this level.
    # Skip sections whose entire content was filtered out (e.g. empty
    # "Stars" or "Watchers" sections on a GitHub sidebar).
    seen: dict[str, int] = {}
    for subsection in node.get("sections", []):
        child = _section_to_toc(subsection)
        if not child:
            continue
        clean_heading = _strip_urls(subsection["heading"])
        seen[clean_heading] = seen.get(clean_heading, 0) + 1

        key = (
            clean_heading
            if seen[clean_heading] == 1
            else f"{clean_heading} ({seen[clean_heading]})"
        )
        result.append({key: child})

    return result


def _parse_error(buf_text: str) -> str:
    """Extract a concise error message from verbose Crawl4AI output."""
    if "ERR_NAME_NOT_RESOLVED" in buf_text:
        return "DNS resolution failed"
    if "ERR_CONNECTION_REFUSED" in buf_text:
        return "Connection refused"
    if "ERR_CONNECTION_TIMED_OUT" in buf_text:
        return "Connection timed out"
    if "ERR_CONNECTION_CLOSED" in buf_text:
        return "Connection closed"
    if "ERR_CONNECTION_RESET" in buf_text:
        return "Connection reset"
    if "net::ERR_" in buf_text:
        match = re.search(r"net::(ERR_\w+)", buf_text)
        if match:
            return f"Network error ({match.group(1)})"
    if "Timeout" in buf_text and "ms exceeded" in buf_text:
        return "Timeout waiting for page to load"
    return "Crawl failed"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_key(url: str) -> str:
    """Derive a short, stable filename from a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16] + ".json"


def _cache_path(url: str) -> Path:
    return _CACHE_DIR / _cache_key(url)


def _cache_is_fresh(path: Path) -> bool:
    """Return True if the cache file exists and is within the TTL."""
    if not path.exists():
        return False
    age = time.time() - os.path.getmtime(str(path))
    return age < _CACHE_TTL_S


def _read_cache_markdown(url: str) -> str | None:
    """Read cached markdown from the unified JSON cache, or ``None``."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("markdown")
    except (OSError, json.JSONDecodeError):
        return None


def _read_cache_links(
    url: str,
) -> dict[str, list[dict[str, Any]]] | None:
    """Read cached navigation links from the unified JSON cache, or ``None``."""
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("links")
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(
    url: str,
    markdown: str,
    links: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Write markdown and links to a unified JSON cache file.

    Each cached entry is a single ``<hash>.json`` file.  The chunked tree
    is always recomputed from markdown on read (never cached) so that
    chunking algorithm changes take effect immediately without cache
    invalidation.
    """
    data: dict[str, Any] = {"markdown": markdown}
    if links is not None:
        data["links"] = links
    path = _cache_path(url)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _evict_if_needed()


def _evict_if_needed() -> None:
    """Remove oldest cache files if count exceeds ``_CACHE_MAX_FILES``.

    Files are sorted by modification time (oldest first); surplus entries
    are deleted.  This runs after every cache write so the limit is a hard
    cap.
    """
    try:
        all_files = sorted(
            _CACHE_DIR.glob("*.json"),
            key=lambda p: os.path.getmtime(str(p)),
        )
    except OSError:
        return  # Directory doesn't exist or isn't readable — ignore.

    if len(all_files) <= _CACHE_MAX_FILES:
        return

    for old_file in all_files[: len(all_files) - _CACHE_MAX_FILES]:
        try:
            old_file.unlink()
        except OSError:
            pass  # Best-effort — don't fail the fetch over cleanup.


# ---------------------------------------------------------------------------
# Table of Contents (chunked-tree based)
# ---------------------------------------------------------------------------
# The old flat ``_build_toc`` / ``_preview_lines`` were replaced by
# ``_parse_chunked`` (full verbose tree) + ``_chunked_to_toc`` (compact
# agent-facing projection).  See the ``Chunked-tree parser`` section above.


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------


def _extract_section(
    content: str,
    *,
    heading: str | None = None,
    line_range: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Extract a section from cached content using the chunked tree.

    Returns ``(markdown, error, info)`` — *error* and *info* are ``None``
    on success without truncation.  *info* carries a human-readable
    truncation note when the result was capped.

    Args:
        content: Full cached markdown content.
        heading: Exact heading text to match (e.g. ``"Tuoreimmat"``).
            Trailing ``" (N)"`` dedup suffixes are stripped for lookup.
        line_range: ``"start-end"`` line range (1-based).

    Raises:
        Never — errors are returned as the second tuple element.
    """
    if line_range is not None:
        return _extract_line_range(content, line_range)

    if heading is not None:
        # Strip optional dedup suffix " (N)" so --heading "Examples (2)"
        # resolves to the second occurrence of "Examples".
        lookup = re.sub(r"\s+\(\d+\)\s*$", "", heading.strip())
        matched_section = _find_section_by_heading(content, lookup)
        if matched_section is None:
            return "", f"Heading '{lookup}' not found on page", None
        return _render_section(matched_section)

    return "", "No section selector provided", None


def _find_section_by_heading(
    content: str,
    heading: str,
) -> dict[str, Any] | None:
    """Walk the chunked tree and return the first section matching *heading*.

    Matching is case-insensitive.  Returns ``None`` if no section is found.
    """
    tree = _parse_chunked(content)

    def _search(node: dict[str, Any]) -> dict[str, Any] | None:
        for section in node.get("sections", []):
            # Strip URLs from the section heading so that headings
            # stored as markdown links (e.g. "[Used by 3k](url)")
            # are matched by the link-text alone.
            if _strip_urls(section["heading"]).lower() == heading.lower():
                return section
            found = _search(section)
            if found:
                return found
        return None

    return _search(tree)


def _render_section(
    section: dict[str, Any],
) -> tuple[str, str | None, str | None]:
    """Render a chunked-tree section (and its subsections) back to markdown.

    Returns ``(markdown, error, info)``.  *info* is a human-readable
    truncation note when the result exceeds ``_TRUNCATION_THRESHOLD``
    characters, or ``None``.

    Walks the section subtree and emits heading lines + chunk text in
    document order so the caller receives a contiguous markdown fragment.
    """
    lines: list[str] = []

    def _walk(node: dict[str, Any]) -> None:
        level = node.get("level", 0)
        heading = node.get("heading")
        if heading is not None and level > 0:
            lines.append("#" * level + " " + heading)
            lines.append("")
        for chunk in node.get("chunks", []):
            lines.append(chunk["text"])
            lines.append("")
        for sub in node.get("sections", []):
            _walk(sub)

    _walk(section)
    markdown = "\n".join(lines).rstrip()

    if len(markdown) > _TRUNCATION_THRESHOLD:
        info = (
            f"Content truncated at {_TRUNCATION_THRESHOLD} characters. "
            f"Use --heading or --line-range to retrieve specific content."
        )
        markdown = markdown[:_TRUNCATION_THRESHOLD] + " ... " + info
        return markdown, None, info

    return markdown, None, None


def _extract_line_range(
    content: str, line_range: str,
) -> tuple[str, str | None, str | None]:
    """Extract lines from a 1-based range string like ``"10-30"``.

    Returns ``(markdown, error, info)``.  *info* is a human-readable
    truncation note when the result exceeds ``_TRUNCATION_THRESHOLD``
    characters, or ``None``.
    """
    try:
        parts = line_range.split("-")
        if len(parts) != 2:
            return "", f"Invalid line range format: '{line_range}' — use 'start-end'", None
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        return "", f"Invalid line range: '{line_range}'", None

    lines = content.splitlines()
    if start < 1:
        start = 1
    if start > len(lines):
        return (
            "",
            f"Line range start {start} exceeds file length ({len(lines)} lines)",
            None,
        )

    end = min(end, len(lines))
    markdown = "\n".join(lines[start - 1:end])

    if len(markdown) > _TRUNCATION_THRESHOLD:
        info = (
            f"Content truncated at {_TRUNCATION_THRESHOLD} characters. "
            f"Use --heading or --line-range to retrieve specific content."
        )
        markdown = markdown[:_TRUNCATION_THRESHOLD] + " ... " + info
        return markdown, None, info

    return markdown, None, None


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


async def _fetch_once(
    url: str,
    wait_until: _WaitUntil,
) -> FetchResult:
    """Perform a single fetch attempt (no caching, no truncation logic).

    Always uses the raw (unfiltered) Crawl4AI config so the cached content
    is stable across calls — section extraction via ``--heading`` /
    ``--line-range`` relies on consistent line numbers from the raw markdown.
    Navigation links and the chunked tree are always computed and persisted
    alongside the markdown cache.
    """
    # All third-party noise (cloakbrowser upgrade nag, crawl4ai logging) is
    # redirected into the buffer so nothing leaks to stderr.
    buf = io.StringIO()
    browser = None

    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            browser = await launch_async(
                headless=True,
                args=[
                    f"--remote-debugging-port={_CDP_PORT}",
                    "--remote-debugging-address=127.0.0.1",
                ],
            )

            browser_config = BrowserConfig(
                browser_mode="cdp",
                cdp_url=f"http://127.0.0.1:{_CDP_PORT}",
            )

            run_config = CrawlerRunConfig(
                wait_until=wait_until,
                page_timeout=_PAGE_TIMEOUT_MS,
                delay_before_return_html=_DELAY_BEFORE_RETURN_HTML_S,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url, config=run_config)

        if result is None:
            return FetchResult(
                success=False,
                error=_parse_error(buf.getvalue()) or "Crawler returned no result",
            )

        if not result.success:
            return FetchResult(
                success=False,
                status_code=result.status_code,
                error=_parse_error(buf.getvalue()),
            )

        # Extract raw markdown (the full page, unfiltered).
        md_obj = result.markdown
        if hasattr(md_obj, "raw_markdown") and md_obj.raw_markdown:
            markdown = md_obj.raw_markdown
        else:
            markdown = str(md_obj) if md_obj else ""

        if not markdown:
            return FetchResult(
                success=True,
                status_code=result.status_code,
                markdown="",
                error="empty",
            )

        # Always extract structured navigation links for caching.
        navigation: dict[str, list[dict[str, Any]]] | None = None
        if result.links:
            navigation = {
                "internal": [
                    {"href": link["href"], "text": link["text"]}
                    for link in result.links.get("internal", [])
                ],
                "external": [
                    {"href": link["href"], "text": link["text"]}
                    for link in result.links.get("external", [])
                ],
            }

        # Parse the markdown into a verbose chunked tree — computed once
        # per fetch so it is available for caching and truncation logic.
        chunked_tree = _parse_chunked(markdown)

        return FetchResult(
            success=True,
            status_code=result.status_code,
            markdown=markdown,
            navigation=navigation,
            chunked=chunked_tree,
            total_chars=len(markdown),
        )

    finally:
        if browser is not None:
            await browser.close()


def _truncation_message() -> str:
    """Minimal markdown placeholder when content exceeds the threshold.

    The full explanation lives in ``_truncation_info`` (returned via the
    ``info`` field), not duplicated here.
    """
    return " ... "


def _truncation_info(total_chars: int, markdown: str = "") -> str:
    """Explain truncation so the agent knows what happened and what to do.

    Appends a feed-page warning when the markdown has very few blank lines
    and a high density of links — typical of news feed / link-directory
    pages where the chunked ToC may be unreliable.
    """
    msg = (
        f"Content exceeds the {_TRUNCATION_THRESHOLD} character limit "
        f"({total_chars} chars total). Full content stored in cache. "
        f"Use `toc` for navigation, or --heading / --line-range "
        f"to retrieve specific content (capped at "
        f"{_TRUNCATION_THRESHOLD} chars)."
    )
    if markdown and _is_feed_page(markdown):
        msg += (
            " WARNING: this page may be a feed/directory — the ToC parsing "
            "may be misleading/incomplete. Try --navigation for structured "
            "link extraction or --line-range for partial reading."
        )
    return msg


def _is_feed_page(markdown: str) -> bool:
    """Detect feed-style pages (dense links, few paragraph breaks).

    News sites and link directories often render as long link streams
    with few blank-line separators — the chunked-tree ToC is less useful
    on these pages.  Returns ``True`` when both conditions hold:

    * blank-line rate < 10 % of total lines
    * link rate > 30 % of total lines

    Blank lines are counted as runs of 2+ consecutive newlines (``\\n\\n``,
    ``\\n\\n\\n``, …) — a triple newline counts as **one** blank-line gap,
    not two.
    """
    total_lines = markdown.count("\n") + 1
    if total_lines == 0:
        return False
    # Count each run of 2+ consecutive newlines as one blank-line gap.
    nl_count = len(_RE_BLANK_LINE_RUN.findall(markdown))
    nl_rate = nl_count / total_lines
    link_rate = markdown.count("](http") / total_lines
    return nl_rate < 0.1 and link_rate > 0.3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
    heading: str | None = None,
    line_range: str | None = None,
    refresh_cache: bool = False,
    include_navigation: bool = False,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    Uses raw (unfiltered) markdown for caching — section extraction via
    ``heading`` / ``line_range`` always operates on consistent content
    regardless of flags used on previous calls.

    When content exceeds the truncation threshold (10 000 chars), the full
    content is saved to a disk cache and the result includes a compact
    table of contents (chunk triples + nested section objects) instead
    of the raw markdown.  Agents can then retrieve specific sections via
    ``heading`` or ``line_range`` parameters — which read directly from
    cache.  Retrieved content is also capped at the same threshold.

    Navigation links (internal/external) are extracted during every fresh
    crawl and persisted in the same cache file.  When
    ``include_navigation=True``, they are returned on cache hits too.

    Args:
        url: The URL to fetch.
        wait_until: Playwright navigation event to wait for.
        heading: Exact heading text to extract from cache (case-insensitive).
            Dedup suffix ``" (N)"`` is stripped before lookup.
        line_range: ``"start-end"`` line range to extract from cache
            (1-based).  Content is capped at ``_TRUNCATION_THRESHOLD``
            characters.
        refresh_cache: If ``True``, always refetch from the web, ignoring any
            cached content.
        include_navigation: If ``True``, include extracted page links
            (internal/external) in the result.

    Returns:
        ``FetchResult`` — never ``None``.

    Side effects:
        Launches/takes down a CloakBrowser subprocess per fresh fetch.
        Writes/reads unified JSON cache files to ``tmp/aivocode/cache/``.
    """
    # ── Section extraction from cache (no fetch needed if fresh) ──────────
    wants_section = heading is not None or line_range is not None

    if wants_section and not refresh_cache:
        cached = _read_cache_markdown(url)
        if cached is not None and _cache_is_fresh(_cache_path(url)):
            md, err, info = _extract_section(
                cached,
                heading=heading,
                line_range=line_range,
            )
            return FetchResult(
                success=err is None,
                markdown=md,
                error=err,
                info=info,
                total_chars=len(md),
            )
        # Cache missing or stale — fetch first, then extract from result.

    # ── Cache hit (no section requested, not refreshing) ─────────────────
    if not wants_section and not refresh_cache and _cache_is_fresh(_cache_path(url)):
        cached_md = _read_cache_markdown(url)
        if cached_md is not None:
            # Restore navigation from the unified cache when requested.
            nav = _read_cache_links(url) if include_navigation else None
            # If navigation was requested but the cache has no links
            # (page was cached before links were stored in the unified
            # format), fall through to a fresh fetch.
            if nav is not None or not include_navigation:
                # Always recompute the chunked tree from markdown rather
                # than trusting a cached version — the chunking algorithm
                # may have changed since the cache was written.
                return _result_with_truncation(
                    cached_md, navigation=nav, chunked=None,
                )

    # ── Fresh fetch ──────────────────────────────────────────────────────
    result = await _fetch_once(url, wait_until)
    if not result.success:
        return result

    # Persist to unified JSON cache (markdown + links).
    full_markdown = result.markdown
    _write_cache(
        url,
        full_markdown,
        links=result.navigation,
    )

    # If a section was requested, extract it from the fresh content.
    if wants_section:
        md, err, info = _extract_section(
            full_markdown,
            heading=heading,
            line_range=line_range,
        )
        return FetchResult(
            success=err is None,
            markdown=md,
            navigation=result.navigation if include_navigation else None,
            error=err,
            info=info,
            total_chars=len(md),
        )

    # Full result — apply truncation if needed.
    return _result_with_truncation(
        full_markdown,
        navigation=result.navigation if include_navigation else None,
        chunked=result.chunked,
    )


def _result_with_truncation(
    markdown: str,
    navigation: dict[str, list[dict[str, Any]]] | None = None,
    chunked: dict[str, Any] | None = None,
) -> FetchResult:
    """Build a FetchResult with optional truncation and compact ToC.

    If *chunked* is ``None`` (old cache without it, or not yet computed),
    the verbose chunked tree is generated on the fly from *markdown*.
    """
    total_chars = len(markdown)
    if total_chars <= _TRUNCATION_THRESHOLD:
        return FetchResult(
            success=True,
            markdown=markdown,
            navigation=navigation,
            total_chars=total_chars,
        )

    # Ensure we have a chunked tree — compute it if missing.
    if chunked is None:
        chunked = _parse_chunked(markdown)

    toc = _chunked_to_toc(chunked)
    return FetchResult(
        success=True,
        markdown=_truncation_message(),
        navigation=navigation,
        toc=toc,
        info=_truncation_info(total_chars, markdown),
        total_chars=total_chars,
    )
