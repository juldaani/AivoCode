"""Stealth web page fetching library — CloakBrowser + Crawl4AI.

What this module provides
- FetchResult: dataclass holding markdown, success flag, HTTP status, error,
  structured links, ToC entries, and truncation metadata.
- fetch_urls(): async function — single public entry point.  Handles full-page
  fetches (with truncation / ToC), single-section extraction, and multi-section
  extraction with a single cache-seed fetch.
- result_to_output_json(): serialize any FetchResult to the standard
  agent-facing JSON format (indent‑2 wrapper, compact ToC field).

Why this exists
- Single entry point for web fetching — used by CLI, Python agents, and
  future transport layers without modification.
- Content-aware: large pages (> 10 000 chars) are automatically truncated to a
  table of contents with section previews, preventing agents from pulling
  huge pages into context.  Full content is cached on disk for section-level
  retrieval on demand (also capped at 10 000 chars).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import socket
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, List, Tuple

import Stemmer
import bm25s
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
    url: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum number of concurrent browser launches/crawls.  Keeps memory
# bounded while allowing genuinely parallel fetches.  Further callers queue
# until a slot frees.
_FETCH_CONCURRENCY: int = 4
_FETCH_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

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

# Character thresholds used exclusively by the webfetch API.
# ---------------------------------------------------------------------------
# ToC trigger — when a full-page fetch exceeds this, the result is replaced
# with a compact table of contents.  Overridable via ``--limit`` CLI flag.
_WEBFETCH_TRUNCATION_THRESHOLD: int = 20_000

# Section‑extraction cap — extracted headings / line ranges are hard‑capped
# at this character count.  Independent of ``--limit`` to keep a separate
# safety net for agent context windows.
_WEBFETCH_SECTION_TRUNCATION_THRESHOLD: int = 10_000

# Maximum number of text-chunk previews to include per section/node in the
# compact ToC, keyed by section depth (0 = root, 1 = H1, …).  Depths beyond
# the last index use the final value.  Used as the default (un‑pruned) cap.
_TOC_MAX_CHUNKS_PER_DEPTH: list[int] = [15]

# Pruned per‑depth caps applied when the ToC is both large (> 50 000 chars
# compact) and achieves poor compression (< 10× vs raw markdown).  Deeper
# sections get fewer previews — typical of reference docs where H4+ headings
# are footnotes or granular API entries that overwhelm the ToC.
_TOC_MAX_CHUNKS_PER_DEPTH_PRUNED: list[int] = [15, 10, 5, 0]

# Thresholds that trigger the pruned caps.
_TOC_PRUNING_SIZE_THRESHOLD: int = 50_000
_TOC_PRUNING_RATIO_THRESHOLD: float = 10.0

# Minimum character count a chunk must have (after URL stripping) to be
# included in the compact ToC.  Chunks below this are typically pure
# boilerplate (e.g. a single bare URL).  Code blocks are excluded from
# this filter.
_MIN_CHUNK_PREVIEW_CHARS: int = 15

# Maximum length of a chunk preview string (chars).  Used by _chunk_preview
# and by the ToC projector's truncation indicator.
_PREVIEW_LEN: int = 80

# ── BM25 keyword extraction constants ──────────────────────────────────────
# Min / max top‑K keywords to extract per chunk.
_KW_MIN_K: int = 3
_KW_MAX_K: int = 15

# Adaptive K: one keyword per this many words in the chunk text (ceil).
_KW_WORDS_PER_KEYWORD: int = 12

# Character threshold (below which keywords are omitted from the ToC).
# 2 × the preview length.
_KW_TOC_CHARS_THRESHOLD: int = 160

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
_CACHE_DIR: Path = Path(".aivocode/cache")

# Cache TTL in seconds.  After this period the cache is considered stale and
# a fresh fetch is triggered automatically.  News sites update frequently;
# 15 min balances freshness against repeated browser launches.
_CACHE_TTL_S: float = 900

# Maximum number of cached files.  When exceeded, the oldest files (by
# modification time) are evicted to keep the cache within bounds.
_CACHE_MAX_FILES: int = 200


def _free_port() -> int:
    """Return a free TCP port on localhost.

    Binds to port 0 so the OS assigns a free ephemeral port, reads the
    assigned port number, then closes the socket.  There is a small TOCTOU
    window between close and reuse, but for short-lived browser launches it
    is acceptable.

    Every ``_fetch_once`` call gets its own port so concurrent crawls run in
    isolated browser processes — no shared CDP endpoint, no cross‑talk.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk_preview(text: str, n: int = _PREVIEW_LEN) -> str:
    """First *n* chars of *text*, URLs stripped, leading whitespace removed,
    hard-cut.

    Strips markdown link syntax and bare URLs so the preview (used in both
    the cached chunked tree and the compact ToC) carries real information
    rather than URL cruft.
    """
    return _strip_urls(text)[:n]


def _chunk_type(text: str) -> str:
    """Classify a chunk as ``"code"``, ``"table"``, ``"blockquote"``, ``"list"``,
    or ``"text"`` based on the first non‑blank line.

    Heuristic:
    - `` ``` `` at line start → code block.
    - ``|`` at line start → table row.
    - ``> `` at line start → blockquote.
    - Bullet (``*``, ``-``, ``+``) or numbered (``1.``) → list.
    - Everything else → text.
    """
    first = text.lstrip()
    if not first:
        return "text"
    first_line = first.split("\n")[0].lstrip()
    if first_line.startswith("```"):
        return "code"
    if first_line.startswith("|"):
        return "table"
    if first_line.startswith("> "):
        return "blockquote"
    if _RE_LIST_ITEM.match(first_line):
        return "list"
    return "text"


def _make_chunk_dict(text: str, start: int, end: int) -> dict[str, Any]:
    """Build a chunk dict with ``text``, ``preview``, ``lines``, and ``type``.

    All chunk creation sites go through this helper so ``type`` is never
    missed and future fields are added in one place.
    """
    return {
        "text": text,
        "preview": _chunk_preview(text),
        "lines": [start, end],
        "type": _chunk_type(text),
    }


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

    # Post-process: merge colon-terminated intro chunks with their
    # following chunk (e.g. "The parameters are:" → table/list below).
    _merge_colon_chunks(root)

    # Post-process: remove empty-anchor chunks (e.g. GitHub's
    # ``[](#section-id)`` heading anchors) that carry no content.
    _remove_empty_anchor_chunks(root)

    # Post-process: merge short orphan chunks (< 150 chars) backward
    # into the previous chunk — eliminates ToC JSON clutter where metadata
    # is larger than the content itself.  Code, table, text+code, and
    # text+table chunks are preserved intact regardless of size.
    #
    # Runs in a loop until convergence: each pass absorbs short chunks
    # into their predecessor.  Stops when no more merges are possible
    # (all remaining candidates are skip-types, section-first orphans
    # with no predecessor, or already above the threshold).
    while _merge_short_chunks(root) > 0:
        pass

    # Post-process: merge moderate chunks (< 300 chars) using a two‑directional
    # heuristic — try backward first (cap result at 800), then forward (same
    # cap), or leave alone.  Reduces ToC entries that are small but not tiny.
    _merge_moderate_chunks(root)

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
                        new_chunks.append(_make_chunk_dict(group_text, line_start + i, line_start + j - 1))
                        i = j  # next group starts at this index
                        group_lines = []
                        group_chars = 0
                    group_lines.append(line_text)
                    group_chars += len(line_text) + (1 if group_lines else 0)
                    j += 1
                # Emit the final (or only) group.
                if group_lines:
                    group_text = "\n".join(group_lines)
                    new_chunks.append(_make_chunk_dict(group_text, line_start + i, line_start + j - 1))
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
                        new_chunks.append(
                            _make_chunk_dict(
                                group_text,
                                line_start + i + emitted,
                                line_start + i + emitted + len(group_lines) - 1,
                            )
                        )
                        emitted += len(group_lines)
                        group_lines = []
                        group_items = 0

                    group_lines.extend(subtree)
                    group_items += n_items

                # Emit final group.
                if group_lines:
                    group_text = "\n".join(group_lines)
                    new_chunks.append(
                        _make_chunk_dict(
                            group_text,
                            line_start + i + emitted,
                            line_start + i + emitted + len(group_lines) - 1,
                        )
                    )

                i = j
            else:
                # Single-line chunk (may be merged with neighbours later).
                new_chunks.append(_make_chunk_dict(stripped, line_start + i, line_start + i))
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
            merged.append(_make_chunk_dict(cur_text, cur_start, cur_end))
            cur_text = nxt_text
            cur_start = nxt["lines"][0]
            cur_end = nxt["lines"][1]
            cur_is_code = nxt_is_code
            cur_is_group = nxt_is_group

    # Emit the trailing accumulated chunk.
    merged.append(_make_chunk_dict(cur_text, cur_start, cur_end))

    return merged


# ── Post‑processing merge: colon‑terminated intro → next chunk ──────────

# Max character length of a colon‑terminated intro chunk to trigger the
# merge.  Longer chunks that end with ":" (e.g. a full sentence) are left
# alone — the colon is likely part of the sentence, not an introduction
# to the next chunk.
_COLON_MERGE_MAX_CHARS: int = 200

# Max character length of a chunk to trigger the short‑chunk merge step.
# Chunks below this threshold that are NOT code, table, text+code, or
# text+table are merged backward into the previous chunk to reduce ToC JSON
# clutter.
_SHORT_CHUNK_MAX_CHARS: int = 150

# Moderate-chunk merge: chunks below this length trigger the merge heuristic.
# Two-directional with a result-size cap to avoid producing over-large chunks.
_MODERATE_CHUNK_MAX_CHARS: int = 300
_MODERATE_CHUNK_RESULT_CAP: int = 800


def _merge_colon_chunks(tree: dict[str, Any]) -> None:
    """Merge a short colon‑terminated chunk with the following chunk.

    Walks every section in the tree.  For each pair of consecutive chunks
    where the first ends with ``:`` and has < ``_COLON_MERGE_MAX_CHARS``
    chars, the two chunks are fused into one (text joined by ``\\n``,
    line range spans both).

    The merged chunk inherits the **second** chunk's type — the colon‑line
    is typically a human‑readable lead‑in to a table, code block, or list.
    """
    for section in tree.get("sections", []):
        _merge_colon_chunks(section)

    chunks = tree.get("chunks")
    if not chunks or len(chunks) < 2:
        return

    merged: list[dict[str, Any]] = []
    i = 0
    while i < len(chunks):
        cur = chunks[i]
        if (
            i + 1 < len(chunks)
            and cur["text"].rstrip().endswith(":")
            and len(cur["text"]) < _COLON_MERGE_MAX_CHARS
        ):
            nxt = chunks[i + 1]
            fused_text = cur["text"] + "\n" + nxt["text"]
            fused = _make_chunk_dict(
                fused_text,
                cur["lines"][0],
                nxt["lines"][1],
            )
            # Override the auto‑detected type — the fused chunk is an
            # intro‑text followed by the second chunk's content, so the
            # combined type reflects both (e.g. "text+code", "text+table").
            fused["type"] = "text+" + nxt.get("type", "text")
            merged.append(fused)
            i += 2
        else:
            merged.append(cur)
            i += 1

    tree["chunks"] = merged


def _remove_empty_anchor_chunks(tree: dict[str, Any]) -> None:
    """Remove chunks whose entire text is empty-anchor markdown links.

    Walks every section in the tree and drops chunks that consist only of
    ``[](url)`` patterns — these carry no textual content and would
    otherwise pollute the ToC and keyword index.
    """
    for section in tree.get("sections", []):
        _remove_empty_anchor_chunks(section)

    tree["chunks"] = [
        c for c in tree.get("chunks", [])
        if not _is_empty_anchor_chunk(c["text"])
    ]


def _is_empty_anchor_chunk(text: str) -> bool:
    """Return ``True`` if *text* consists solely of empty-anchor markdown links.

    Catches patterns like ``[](https://...#section)`` or ``[](url)`` where
    the alt‑text is empty — these are heading anchors that carry no content.
    Multiple anchors joined by whitespace are also detected.
    """
    if not text.strip():
        return False
    stripped = re.sub(r"\[\]\([^)]*\)", "", text).strip()
    return len(stripped) == 0


# Post‑processing merge: short orphan chunks (< _SHORT_CHUNK_MAX_CHARS),
# merged **backward** into the previous chunk so the meaningful preview text
# survives.  Base types that are semantically atomic — any chunk whose type
# contains one of these (e.g. ``text+code``, ``list+text``, ``text+code+text``)
# is never merged outside the colon‑merge step.
_MERGE_SKIP_BASE_TYPES: frozenset[str] = frozenset({"code", "table", "list", "blockquote"})


def _is_skip_type(chunk_type: str) -> bool:
    """Return ``True`` if *chunk_type* contains any atomic base type.

    Splits on ``+`` and checks for intersection with
    ``_MERGE_SKIP_BASE_TYPES``.  This catches simple types (``code``) and
    composite types from any merge step (``text+list``, ``list+text``,
    ``text+code+text``, etc.).
    """
    parts = chunk_type.split("+")
    return bool(_MERGE_SKIP_BASE_TYPES.intersection(parts))


def _merge_short_chunks(tree: dict[str, Any]) -> int:
    """Merge short orphan chunks (< ``_SHORT_CHUNK_MAX_CHARS`` chars) backward
    into the **previous** chunk.

    Walks every section in the tree.  When a chunk is short and its type is
    NOT in ``_MERGE_SKIP_BASE_TYPES`` (any type containing code, table, list,
    or blockquote), it is absorbed into the end of the
    preceding chunk (text joined by ``\\n``, line range spans both).

    Merging backward preserves the preceding chunk's preview text — the
    orphan is appended after it, not before it.  This is important because
    the first few lines of a chunk determine its ToC preview; merging a
    boilerplate orphan (e.g. "© 2026 GitHub, Inc.") into the front of a
    substantive chunk would replace the useful preview with noise.

    The merged chunk's type follows a same‑type shortcut: when both chunks
    share the same type, the fused chunk keeps that single type (e.g.
    ``text`` + ``text`` → ``text``).  When types differ, the composition is
    preserved with a ``+`` separator (e.g. ``text`` + ``list`` → ``text+list``).

    Returns the total number of merges performed across all sections (0 if
    no chunk was short enough or all candidates were in the skip set).
    Callers use this to detect convergence — a zero return means no further
    progress is possible, even if short chunks remain.
    """
    merges = 0

    for section in tree.get("sections", []):
        merges += _merge_short_chunks(section)

    chunks = tree.get("chunks")
    if not chunks or len(chunks) < 2:
        return merges

    merged: list[dict[str, Any]] = []
    for cur in chunks:
        # Absorb backward into the previous chunk when: this chunk is short,
        # its type is safe to merge, and there IS a previous chunk.
        if (
            len(cur["text"]) < _SHORT_CHUNK_MAX_CHARS
            and not _is_skip_type(cur.get("type", "text"))
            and merged
            and not _is_skip_type(merged[-1].get("type", "text"))
        ):
            prev = merged[-1]
            fused_text = prev["text"] + "\n" + cur["text"]
            fused = _make_chunk_dict(
                fused_text,
                prev["lines"][0],
                cur["lines"][1],
            )
            # Compute merged type: same type → use that type;
            # different types → preserve the composition hint.
            prev_type = prev.get("type", "text")
            cur_type = cur.get("type", "text")
            fused["type"] = prev_type if prev_type == cur_type else f"{prev_type}+{cur_type}"
            merged[-1] = fused
            merges += 1
        else:
            merged.append(cur)

    tree["chunks"] = merged
    return merges


def _merge_moderate_chunks(tree: dict[str, Any]) -> None:
    """Merge medium‑small chunks (< ``_MODERATE_CHUNK_MAX_CHARS`` chars) using
    a two‑directional heuristic.

    For each chunk under 300 chars, try:

    1. **Backward merge** — absorb into the previous chunk.  Skipped when
       the result would exceed ``_MODERATE_CHUNK_RESULT_CAP`` (800 chars).
    2. **Forward merge** (fallback) — absorb the next chunk into this one.
       Skipped when the result would exceed the same cap.

    If neither direction is viable the chunk is left alone.  The scan is a
    single forward pass — ``i`` advances to the next chunk after each
    decision (whether merged or kept).

    Chunks whose type contains any base atomic type from
    ``_MERGE_SKIP_BASE_TYPES`` (code, table, list, or blockquote, including
    all composite forms like ``text+code``, ``list+text``,
    ``text+code+text``) are never merged — they are semantically atomic and
    stay intact regardless of size.  Only the colon‑merge step
    is allowed to fuse those types.

    Merged type logic: same type → single type; different types →
    ``prev_type+nxt_type`` (same convention as the short‑chunk merge).
    """
    for section in tree.get("sections", []):
        _merge_moderate_chunks(section)

    chunks = tree.get("chunks")
    if not chunks or len(chunks) < 2:
        return

    merged: list[dict[str, Any]] = []
    i = 0
    while i < len(chunks):
        cur = chunks[i]
        cur_len = len(cur["text"])

        if cur_len >= _MODERATE_CHUNK_MAX_CHARS:
            # Chunk is already large enough — keep as-is.
            merged.append(cur)
            i += 1
            continue

        # Skip types that are semantically atomic — any type containing
        # code, table, or list (same base set as the short‑chunk merge).
        if _is_skip_type(cur.get("type", "text")):
            merged.append(cur)
            i += 1
            continue

        # ── Step 1: try backward merge ────────────────────────────────
        if merged and not _is_skip_type(merged[-1].get("type", "text")):
            prev = merged[-1]
            combined_len = len(prev["text"]) + cur_len + 1  # +1 for \n
            if combined_len <= _MODERATE_CHUNK_RESULT_CAP:
                fused_text = prev["text"] + "\n" + cur["text"]
                fused = _make_chunk_dict(
                    fused_text,
                    prev["lines"][0],
                    cur["lines"][1],
                )
                prev_type = prev.get("type", "text")
                cur_type = cur.get("type", "text")
                fused["type"] = prev_type if prev_type == cur_type else f"{prev_type}+{cur_type}"
                merged[-1] = fused
                i += 1
                continue

        # ── Step 2: try forward merge ─────────────────────────────────
        if i + 1 < len(chunks) and not _is_skip_type(chunks[i + 1].get("type", "text")):
            nxt = chunks[i + 1]
            combined_len = cur_len + len(nxt["text"]) + 1  # +1 for \n
            if combined_len <= _MODERATE_CHUNK_RESULT_CAP:
                fused_text = cur["text"] + "\n" + nxt["text"]
                fused = _make_chunk_dict(
                    fused_text,
                    cur["lines"][0],
                    nxt["lines"][1],
                )
                cur_type = cur.get("type", "text")
                nxt_type = nxt.get("type", "text")
                fused["type"] = cur_type if cur_type == nxt_type else f"{cur_type}+{nxt_type}"
                merged.append(fused)
                i += 2
                continue

        # Neither merge viable — keep cur as-is.
        merged.append(cur)
        i += 1

    tree["chunks"] = merged


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
    # Skip chunks that are pure empty-anchor links — e.g. GitHub's
    # auto-generated ``[](#section-id)`` heading anchors.
    if _is_empty_anchor_chunk(text):
        return
    parent["chunks"].append(_make_chunk_dict(text, start, end))


# ---------------------------------------------------------------------------
# BM25 keyword extraction — writes keywords back into the chunked tree
# ---------------------------------------------------------------------------


def _flatten_chunk_dicts(tree: dict[str, Any]) -> List[dict[str, Any]]:
    """Walk *tree* and return a flat list of every chunk dict (by reference).

    Because the returned list holds the **same dict objects** that live in
    the tree, mutations (e.g. adding ``bm25_keywords``) are visible in the
    original tree.
    """
    result: List[dict[str, Any]] = []
    for chunk in tree.get("chunks", []):
        result.append(chunk)
    for sub in tree.get("sections", []):
        result.extend(_flatten_chunk_dicts(sub))
    return result


def _get_top_bm25_keywords(
    bm25_obj: bm25s.BM25,
    token_ids_per_doc: List[List[int]],
    id_to_token: dict[int, str],
    top_n: int = 3,
) -> List[List[str]]:
    """Return top-N (token_string) lists for each document from the CSR matrix.

    Reads the internal CSR-format term-document matrix from
    ``bm25_obj.scores``, collects every term that appears in a given
    document, sorts by the BM25 weight, and returns the top *top_n*
    **token strings only** (scores are discarded — the keywords are for
    informational display, not ranking).
    """
    data = bm25_obj.scores["data"]
    indices = bm25_obj.scores["indices"]
    indptr = bm25_obj.scores["indptr"]
    num_terms = len(indptr) - 1

    results: List[List[str]] = []
    for doc_id in range(len(token_ids_per_doc)):
        term_scores: List[Tuple[str, float]] = []
        for term_id in range(num_terms):
            start = indptr[term_id]
            end = indptr[term_id + 1]
            for pos in range(start, end):
                if indices[pos] == doc_id:
                    token_str = id_to_token.get(term_id, f"<unk:{term_id}>")
                    term_scores.append((token_str, float(data[pos])))
                    break
        term_scores.sort(key=lambda x: x[1], reverse=True)
        results.append([t for t, _ in term_scores[:top_n]])

    return results


def _add_bm25_keywords_to_tree(tree: dict[str, Any]) -> None:
    """Compute BM25 keywords for every chunk in *tree* and write them back.

    Steps:
    1. Flatten all chunk dicts from the tree (by reference).
    2. Tokenize the corpus with the English stemmer.
    3. Build a ``bm25s.BM25`` index.
    4. For each chunk, compute an adaptive K from the word count
       (clamped to ``[_KW_MIN_K, _KW_MAX_K]``), extract top-K terms,
       and store the token list in ``chunk["bm25_keywords"]``.

    Keywords are ALWAYS computed for every chunk (ground truth), regardless
    of whether the ToC projector chooses to emit them.
    """
    chunk_dicts = _flatten_chunk_dicts(tree)
    if not chunk_dicts:
        return

    # Build corpus from chunk text.
    corpus = [c["text"] for c in chunk_dicts]
    stemmer = Stemmer.Stemmer("english")
    token_ids, vocab = bm25s.tokenize(
        corpus, stopwords="en", stemmer=stemmer, return_ids=True,
    )
    id_to_token: dict[int, str] = {v: k for k, v in vocab.items()}

    # Compute word counts for adaptive K sizing.
    word_counts: List[int] = []
    for c in chunk_dicts:
        # Count non-empty lines / whitespace-delimited tokens as a cheap
        # word‑count heuristic that does not need a separate tokenizer.
        text = c["text"]
        if text.strip():
            word_counts.append(len(text.split()))
        else:
            word_counts.append(0)

    # Adaptive K: ceil(word_count / _KW_WORDS_PER_KEYWORD), clamped.
    # We compute the max across all chunks first, then extract at that level
    # and trim per-chunk afterward — this is cheaper than indexing per chunk.
    top_n_all = min(
        _KW_MAX_K,
        max(
            _KW_MIN_K,
            -(-max(word_counts) // _KW_WORDS_PER_KEYWORD) if word_counts else _KW_MIN_K,
        ),
    )

    bm25 = bm25s.BM25()
    bm25.index(token_ids)
    all_keywords = _get_top_bm25_keywords(
        bm25, token_ids, id_to_token, top_n=top_n_all,
    )

    # Write keywords back into each chunk dict (mutates tree in-place).
    for chunk, kws, wc in zip(chunk_dicts, all_keywords, word_counts):
        needed = max(
            _KW_MIN_K,
            min(_KW_MAX_K, -(-wc // _KW_WORDS_PER_KEYWORD)),
        )
        chunk["bm25_keywords"] = kws[:needed]


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


def _chunked_to_toc(
    tree: dict[str, Any],
    max_per_depth: list[int] | None = None,
) -> list[Any]:
    """Project the verbose cached chunked tree into a compact ToC.

    The compact format is an ordered array where:
- Strings ``"904-926 ‖ type ‖ kw1,kw2 ‖ preview..."`` are chunks
      (keyword field omitted for chunks ≤ ``_KW_TOC_CHARS_THRESHOLD``).
    - ``{"type": "omitted", "n_omitted": N, "lines": [first, last],
      "info": "…"}`` sentinels mark chunks that were skipped due to the
      per‑depth cap.
    - ``{"Heading Name": [...]}`` objects are subsections.

    Duplicate heading names at the same level get a ``" (N)"`` suffix.
    The root ``type`` / ``level`` keys and full ``text`` values are
    dropped — only previews and line ranges are retained.

    *max_per_depth* controls how many chunk previews to emit per section
    at each nesting depth.  Defaults to ``_TOC_MAX_CHUNKS_PER_DEPTH``.
    """
    if max_per_depth is None:
        max_per_depth = _TOC_MAX_CHUNKS_PER_DEPTH
    return _section_to_toc(tree, depth=0, max_per_depth=max_per_depth)


def _section_to_toc(
    node: dict[str, Any],
    *,
    depth: int = 0,
    max_per_depth: list[int] | None = None,
) -> list[Any]:
    """Recursively convert a single node to ToC array entries.

    Caps text-chunk previews per depth using *max_per_depth* (index =
    section nesting depth; depths beyond the list use the last value).
    Skipped chunks are summarised by a sentinel triple.
    """
    if max_per_depth is None:
        max_per_depth = _TOC_MAX_CHUNKS_PER_DEPTH
    # Per-depth cap — clamp to the last element for deep nesting.
    cap = max_per_depth[min(depth, len(max_per_depth) - 1)]

    result: list[Any] = []
    chunks: list[dict[str, Any]] = node.get("chunks", [])

    if cap == 0 and chunks:
        # No previews at this depth — emit a single sentinel covering
        # all chunks so the section heading is still navigable.
        first = chunks[0]["lines"][0]
        last = chunks[-1]["lines"][1]
        result.append({
            "type": "omitted",
            "n_omitted": len(chunks),
            "lines": [first, last],
            "info": (
                f"… {len(chunks)} chunks — use --heading to expand all, "
                f"or --line-range to read selectively"
            ),
        })
    elif cap > 0:
        # Emit up to *cap* chunk previews — cap with sentinel if there are
        # more.  Skip trivially-short non-code chunks whose content was
        # mostly URLs.
        emitted = 0
        i = -1
        for i, chunk in enumerate(chunks):
            text = chunk["text"].strip()
            if not text.startswith("```"):
                if len(_strip_urls(chunk["text"])) < _MIN_CHUNK_PREVIEW_CHARS:
                    continue

            ls, le = chunk["lines"]
            # Build the compact chunk string:
            #   "ls-le ‖ type ‖ kw1,kw2 ‖ preview..."
            preview_text = chunk["preview"]
            # Append "..." when the preview was hard-truncated.
            if len(preview_text) >= _PREVIEW_LEN:
                preview_text += "..."
            parts = [
                f"{ls}-{le}",
                chunk.get("type", "text"),
            ]
            chunk_n_chars = len(chunk["text"])
            if chunk_n_chars > _KW_TOC_CHARS_THRESHOLD:
                kws = ",".join(chunk.get("bm25_keywords", []))
                if kws:
                    parts.append(kws)
            parts.append(preview_text)
            result.append(" ‖ ".join(parts))
            emitted += 1

            if emitted >= cap:
                break

        # Only add sentinel when we stopped early due to the cap.
        if emitted >= cap and i + 1 < len(chunks):
            skipped = len(chunks) - (i + 1)
            first = chunks[i + 1]["lines"][0]
            last = chunks[-1]["lines"][1]
            result.append({
                "type": "omitted",
                "n_omitted": skipped,
                "lines": [first, last],
                "info": (
                    f"… {skipped} more chunks — use --heading to expand all, "
                    f"or --line-range to read selectively"
                ),
            })

    # Subsections — deduplicate heading names within this level.
    # Skip sections whose entire content was filtered out (e.g. empty
    # "Stars" or "Watchers" sections on a GitHub sidebar).
    seen: dict[str, int] = {}
    for subsection in node.get("sections", []):
        child = _section_to_toc(
            subsection,
            depth=depth + 1,
            max_per_depth=max_per_depth,
        )
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
    """Read cached markdown from the unified JSON cache, or ``None``.

    Returns ``None`` when the cache file stores a ``url`` field that does
    not match *url* — the two URLs produce different SHA‑256 keys, so a
    mismatch means the cache entry was corrupted (race, manual tamper,
    filesystem error).  Old cache files without a ``url`` field are
    treated as trusted; they expire naturally after the TTL.
    """
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored_url = data.get("url")
        if stored_url is not None and stored_url != url:
            return None  # cache entry belongs to a different URL
        return data.get("markdown")
    except (OSError, json.JSONDecodeError):
        return None


def _read_cache_links(
    url: str,
) -> dict[str, list[dict[str, Any]]] | None:
    """Read cached navigation links from the unified JSON cache, or ``None``.

    Same URL‑verification semantics as ``_read_cache_markdown``.
    """
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stored_url = data.get("url")
        if stored_url is not None and stored_url != url:
            return None  # cache entry belongs to a different URL
        return data.get("links")
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(
    url: str,
    markdown: str,
    links: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Write markdown, links, and source URL to a unified JSON cache file.

    Each cached entry is a single ``<hash>.json`` file.  The chunked tree
    is always recomputed from markdown on read (never cached) so that
    chunking algorithm changes take effect immediately without cache
    invalidation.

    The ``url`` field in the JSON serves as a self‑check — readers can
    detect cache entries that were accidentally written for a different
    URL (e.g. due to a page‑level browser race) and treat them as misses.
    """
    data: dict[str, Any] = {"url": url, "markdown": markdown}
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
    truncation note when the result exceeds
    ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD`` characters, or ``None``.

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

    if len(markdown) > _WEBFETCH_SECTION_TRUNCATION_THRESHOLD:
        info = (
            f"Content truncated at {_WEBFETCH_SECTION_TRUNCATION_THRESHOLD} characters. "
            f"Use --heading or --line-range to retrieve specific content."
        )
        markdown = markdown[:_WEBFETCH_SECTION_TRUNCATION_THRESHOLD] + " ... " + info
        return markdown, None, info

    return markdown, None, None


def _extract_line_range(
    content: str, line_range: str,
) -> tuple[str, str | None, str | None]:
    """Extract lines from a 1-based range string like ``"10-30"``.

    Returns ``(markdown, error, info)``.  *info* is a human-readable
    truncation note when the result exceeds
    ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD`` characters, or ``None``.
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

    if len(markdown) > _WEBFETCH_SECTION_TRUNCATION_THRESHOLD:
        info = (
            f"Content truncated at {_WEBFETCH_SECTION_TRUNCATION_THRESHOLD} characters. "
            f"Use --heading or --line-range to retrieve specific content."
        )
        markdown = markdown[:_WEBFETCH_SECTION_TRUNCATION_THRESHOLD] + " ... " + info
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
    result = None

    try:
        # ── Rate-limit concurrent browser launches ────────────────────
        # The semaphore caps live crawls at _FETCH_CONCURRENCY (4) so
        # memory stays bounded.  Cache reads (no fresh fetch) never
        # reach here, so cache hits remain fully concurrent.
        async with _FETCH_SEMAPHORE:
            # Allocate a free port so this crawl gets its own isolated
            # browser process.  No shared CDP endpoint, no cross‑talk.
            port = _free_port()

            with redirect_stdout(buf), redirect_stderr(buf):
                browser = await launch_async(
                    headless=True,
                    args=[
                        f"--remote-debugging-port={port}",
                        "--remote-debugging-address=127.0.0.1",
                    ],
                )

                browser_config = BrowserConfig(
                    browser_mode="cdp",
                    cdp_url=f"http://127.0.0.1:{port}",
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
                url=url,
            )

        if not result.success:
            return FetchResult(
                success=False,
                status_code=result.status_code,
                error=_parse_error(buf.getvalue()),
                url=url,
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
                url=url,
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
            url=url,
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


def _truncation_info(total_chars: int, markdown: str = "", *, limit: int = 20_000) -> str:
    """Explain truncation so the agent knows what happened and what to do.

    Message order: truncation notice → ToC format → omitted sentinels →
    feed-page warning (if applicable).

    *limit* is the webfetch ToC threshold (overridable via ``--limit``).
    The section‑extraction cap message references the dedicated
    ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD`` constant (10 000 chars).
    """
    msg = (
        f"Content exceeds the {limit} character limit "
        f"({total_chars} chars total). Full content stored in cache. "
        f"Use `toc` for navigation -> --heading / --line-range "
        f"to retrieve specific content (capped at "
        f"{_WEBFETCH_SECTION_TRUNCATION_THRESHOLD} chars)."
    )
    msg += "\n\n" + _bm25_info()
    msg += (
        "\n\nSome sections contain omitted-chunk sentinels "
        "(type `omitted`). Each sentinel collapses N chunks with "
        "their first and last line numbers. "
        "Use --heading to expand that section in the ToC, "
        "or --line-range to read a specific range directly."
    )
    if markdown and _is_feed_page(markdown):
        msg += (
            "\n\nWARNING: this page may be a feed/directory — the ToC parsing "
            "may be misleading/incomplete. Try --navigation for structured "
            "link extraction or --line-range for partial reading."
        )
    return msg


def _bm25_info() -> str:
    """Return a one‑liner explaining the ToC compact‑string format."""
    return (
        "ToC chunk format: "
        "`lines ‖ type ‖ keywords ‖ preview...`. "
        "`...` = preview truncated. "
        "Keywords: top BM25 relevance terms (English‑stemmed) on chunks > {} chars."
    ).format(_KW_TOC_CHARS_THRESHOLD)


def _is_feed_page(markdown: str) -> bool:
    """Detect feed-style pages (dense short lines, many links).

    News sites and link directories produce many short (50‑150 char) lines
    separated by ``\\n`` with a high density of markdown links.  Pages with
    long (300‑600 char) ``\\n``-delimited paragraphs are well-formed prose
    and should NOT be flagged, even if they have few blank lines.

    Returns ``True`` when **either** condition holds:

    * average chars per line < 150 (short lines = feed / directory)
    * link rate > 30 % of total lines (link density)

    Average chars per line is computed over **all** lines (including blank
    lines, which contribute 0 chars) — this naturally penalises sparse
    content without needing a separate blank-line metric.
    """
    total_lines = markdown.count("\n") + 1
    if total_lines == 0:
        return False
    avg_chars = len(markdown) / total_lines
    link_rate = markdown.count("](http") / total_lines
    return avg_chars < 150 or link_rate > 0.3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _fetch_url(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
    heading: str | None = None,
    line_range: str | None = None,
    refresh_cache: bool = False,
    include_navigation: bool = False,
    limit: int = _WEBFETCH_TRUNCATION_THRESHOLD,
) -> FetchResult:
    """Fetch a URL via CloakBrowser + Crawl4AI and return structured results.

    Uses raw (unfiltered) markdown for caching — section extraction via
    ``heading`` / ``line_range`` always operates on consistent content
    regardless of flags used on previous calls.

    When content exceeds *limit* chars (default 20 000), the full content
    is saved to a disk cache and the result includes a compact table of
    contents (chunk triples + nested section objects) instead of the raw
    markdown.  Agents can then retrieve specific sections via ``heading``
    or ``line_range`` parameters — which read directly from cache.
    Retrieved content is capped at ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD`` chars (hard
    limit, independent of *limit*).

    Navigation links (internal/external) are extracted during every fresh
    crawl and persisted in the same cache file.  When
    ``include_navigation=True``, they are returned on cache hits too.

    Args:
        url: The URL to fetch.
        wait_until: Playwright navigation event to wait for.
        heading: Exact heading text to extract from cache (case-insensitive).
            Dedup suffix ``" (N)"`` is stripped before lookup.
        line_range: ``"start-end"`` line range to extract from cache
            (1-based).  Content is capped at ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD``
            characters.
        refresh_cache: If ``True``, always refetch from the web, ignoring any
            cached content.
        include_navigation: If ``True``, include extracted page links
            (internal/external) in the result.
        limit: Character threshold for the ToC — full-page fetches exceeding
            this return a compact ToC instead of raw markdown.  Does not
            affect section extraction (which uses ``_WEBFETCH_SECTION_TRUNCATION_THRESHOLD``).

    Returns:
        ``FetchResult`` — never ``None``.

    Side effects:
        Launches/takes down a CloakBrowser subprocess per fresh fetch.
        Writes/reads unified JSON cache files to ``.aivocode/cache/``.
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
                url=url,
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
                    cached_md, navigation=nav, chunked=None, limit=limit,
                    url=url,
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
            url=url,
        )

    # Full result — apply truncation if needed.
    return _result_with_truncation(
        full_markdown,
        navigation=result.navigation if include_navigation else None,
        chunked=result.chunked,
        limit=limit,
        url=url,
    )


def _result_with_truncation(
    markdown: str,
    navigation: dict[str, list[dict[str, Any]]] | None = None,
    chunked: dict[str, Any] | None = None,
    *,
    url: str = "",
    limit: int = _WEBFETCH_TRUNCATION_THRESHOLD,
) -> FetchResult:
    """Build a FetchResult with optional truncation and compact ToC.

    When *markdown* exceeds *limit* chars, replaces it with a compact ToC
    and stores a helpful info message.  Below *limit* the raw markdown is
    returned as-is.

    If *chunked* is ``None`` (old cache without it, or not yet computed),
    the verbose chunked tree is generated on the fly from *markdown*.
    """
    total_chars = len(markdown)
    if total_chars <= limit:
        return FetchResult(
            success=True,
            markdown=markdown,
            navigation=navigation,
            total_chars=total_chars,
            url=url,
        )

    # Ensure we have a chunked tree — compute it if missing.
    if chunked is None:
        chunked = _parse_chunked(markdown)

    # Enrich the chunked tree with BM25 keyword metadata (mutates in-place).
    _add_bm25_keywords_to_tree(chunked)

    toc = _chunked_to_toc(chunked)

    # ── Pruning: re‑build ToC with depth‑aware caps when the ToC is
    # both large and achieves poor compression — typical of reference
    # docs with hundreds of deeply nested sections (e.g. node_fs).
    toc_json = json.dumps(toc, ensure_ascii=False)
    toc_n_chars = len(toc_json)
    if (
        toc_n_chars > _TOC_PRUNING_SIZE_THRESHOLD
        and total_chars / toc_n_chars < _TOC_PRUNING_RATIO_THRESHOLD
    ):
        toc = _chunked_to_toc(chunked, max_per_depth=_TOC_MAX_CHUNKS_PER_DEPTH_PRUNED)

    return FetchResult(
        success=True,
        markdown=_truncation_message(),
        navigation=navigation,
        toc=toc,
        info=_truncation_info(total_chars, markdown, limit=limit),
        total_chars=total_chars,
        url=url,
    )


async def fetch_urls(
    url: str,
    *,
    wait_until: _WaitUntil = _DEFAULT_WAIT_UNTIL,
    headings: list[str] | None = None,
    line_ranges: list[str] | None = None,
    refresh_cache: bool = False,
    include_navigation: bool = False,
    limit: int = _WEBFETCH_TRUNCATION_THRESHOLD,
) -> FetchResult:
    """Fetch *url* (or extract sections from it) and return structured results.

    The single public entry point for web fetching.  Handles three cases:

    1. **No selectors** — returns the full page (truncated to a ToC when the
       content exceeds *limit* chars, default 20 000).
    2. **Single selector** (one heading or one line‑range) — extracts that
       section from the cached page.
    3. **Multiple selectors** — seeds the cache with one fetch, then extracts
       each section and returns combined, annotated markdown joined by
       ``\\n\\n---\\n\\n``.

    Args:
        url: The URL to fetch.
        wait_until: Playwright navigation event.
        headings: Section headings to extract (case‑insensitive).
        line_ranges: ``\"start-end\"`` line ranges to extract (1‑based).
        refresh_cache: If ``True``, always refetch, ignoring cache.
        include_navigation: If ``True``, include extracted page links in the
            result (only applicable when no selectors are given).
        limit: Character count above which a full‑page fetch returns a
            compact ToC instead of raw markdown (default 20 000).

    Returns:
        ``FetchResult`` — never ``None``.

    Side effects:
        Launches/takes down a CloakBrowser subprocess per fresh fetch.
        Writes/reads unified JSON cache files to ``.aivocode/cache/``.
    """
    headings = headings or []
    line_ranges = line_ranges or []
    n_selectors = len(headings) + len(line_ranges)

    # ── Multi‑section path ──────────────────────────────────────────────
    if n_selectors > 1:
        # Seed the cache with one fetch.
        seed = await _fetch_url(
            url, wait_until=wait_until, refresh_cache=refresh_cache,
            limit=limit,
        )
        if not seed.success:
            return FetchResult(
                success=False,
                markdown="",
                error=f"Failed to fetch {url}: {seed.error}",
                url=url,
            )

        successes: list[str] = []
        errors: list[str] = []

        for heading in headings:
            r = await _fetch_url(
                url, wait_until=wait_until, heading=heading,
            )
            if r.success and r.markdown:
                successes.append(f"[heading: {heading}]\n\n{r.markdown}")
            else:
                errors.append(f"heading '{heading}': {r.error or 'no content'}")

        for lr in line_ranges:
            r = await _fetch_url(
                url, wait_until=wait_until, line_range=lr,
            )
            if r.success and r.markdown:
                successes.append(f"[lines: {lr}]\n\n{r.markdown}")
            else:
                errors.append(f"line-range '{lr}': {r.error or 'no content'}")

        combined = "\n\n---\n\n".join(successes) if successes else ""
        return FetchResult(
            success=bool(successes),
            markdown=combined,
            error="; ".join(errors) if errors else None,
            url=url,
        )

    # ── Single / no selector → delegate to _fetch_url ───────────────────
    heading = headings[0] if headings else None
    line_range = line_ranges[0] if line_ranges else None
    return await _fetch_url(
        url,
        wait_until=wait_until,
        heading=heading,
        line_range=line_range,
        refresh_cache=refresh_cache,
        include_navigation=include_navigation,
        limit=limit,
    )


def result_to_output_json(result: FetchResult, *, compact_toc: bool = True) -> str:
    """Serialize a ``FetchResult`` to the standard JSON output format.

    Builds the agent-facing output dict from *result*, strips ``None``-valued
    keys (so the agent sees only meaningful fields), and serializes with
    ``indent=2`` wrapper formatting.

    When *compact_toc* is ``True`` (the default), the ``toc`` field is
    serialized as a single compact line — because the ToC dominates the
    payload and indentation wastes ~66 % on whitespace in deeply nested
    structures.  When ``False``, the entire output uses ``indent=2``,
    producing a human‑readable multi‑line ToC.

    Returns a JSON string ready to ``print``.
    """
    # Compute toc_n_chars from compact JSON — compact is the real content
    # metric regardless of output format.
    toc_n_chars: int | None = None
    if result.toc is not None:
        toc_n_chars = len(json.dumps(result.toc, ensure_ascii=False))

    output: dict[str, Any] = {
        "url": result.url,
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "info": result.info,
        "toc_n_chars": toc_n_chars,
        "markdown": result.markdown,
        "navigation": result.navigation,
        "toc": result.toc,
    }

    # Strip None / null fields.
    output = {k: v for k, v in output.items() if v is not None}

    toc = output.get("toc")
    if toc is None or not compact_toc:
        return json.dumps(output, indent=2, ensure_ascii=False)

    # Marker-replace: serialize wrapper with indent=2, then swap the
    # indented toc for its compact JSON representation.
    output_marker = dict(output)
    output_marker["toc"] = "__TOC__"
    pretty = json.dumps(output_marker, indent=2, ensure_ascii=False)
    return pretty.replace('"__TOC__"', json.dumps(toc, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Chunk flattener — converts the chunked tree into TextNode list for indexing
# ---------------------------------------------------------------------------


def _flatten_chunks(
    tree: dict[str, Any],
    *,
    heading_path: list[str] | None = None,
    include_headers: bool = True,
) -> list[Any]:
    """Flatten a chunked tree into a list of ``TextNode`` objects.

    Each leaf chunk becomes one ``TextNode`` with metadata:
    - ``heading_path``: list of ancestor heading strings (empty for root-level
      chunks).
    - ``lines``: ``[start_1based, end_1based]`` source line range.

    When *include_headers* is ``True``, the chunk text is prefixed with a
    breadcrumb like ``[Section > Subsection]`` to improve both embedding
    quality (semantic context for the chunk) and BM25 term matching
    (heading keywords contribute to retrieval).

    This function lives in ``fetcher.py`` because it is tightly coupled to
    the output shape of ``_parse_chunked``.  It is NOT the only way to
    produce nodes for ``HybridSearcher`` — any list of ``TextNode`` works.

    Args:
        tree: A chunked tree dict as returned by ``_parse_chunked``.
        heading_path: Accumulated heading breadcrumb (used internally during
            recursion — callers pass ``None`` or omit).
        include_headers: Whether to prepend breadcrumbs to chunk text.
            Default ``True``.

    Returns:
        Flat list of ``TextNode`` objects (from ``llama_index.core.schema``).
    """
    # Lazy import — TextNode is only needed for the hybrid search code path,
    # not for normal fetches.
    from llama_index.core.schema import TextNode  # noqa: E402

    heading_path = heading_path or []
    nodes: list[Any] = []

    # Emit nodes for every leaf chunk in this section.
    for chunk in tree.get("chunks", []):
        text: str = chunk["text"]
        if include_headers and heading_path:
            text = f"[{' > '.join(heading_path)}] {text}"

        nodes.append(TextNode(
            text=text,
            metadata={
                "heading_path": list(heading_path),
                "lines": list(chunk["lines"]),
            },
        ))

    # Recurse into child sections.
    for section in tree.get("sections", []):
        heading: str = section.get("heading", "")
        child_path = heading_path + ([heading] if heading else [])
        nodes.extend(
            _flatten_chunks(
                section,
                heading_path=child_path,
                include_headers=include_headers,
            )
        )

    return nodes
