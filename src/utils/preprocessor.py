"""
vietnamese_preprocessor.py
===========================
Production-grade Vietnamese NLP preprocessing pipeline.

Pipeline order per document:
  1. Unicode repair (ftfy)
  2. Structural noise removal (HTML, brackets, separators)
  3. cleantext  (URL / email / phone / currency stripping)
  4. Teencode normalisation   (loaded from external file)
  5. Punctuation normalisation
  6. Whitespace collapse
  7. Word segmentation via underthesea (chunked, process-safe)
  8. Optional stopword removal
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import ftfy
from pymongo import MongoClient, UpdateOne
from underthesea import word_tokenize

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_SEGMENT_CHARS: int = 10_000   # chunk texts longer than this before tokenising

# Compiled once at module level (process-safe, picklable)
_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"<[^>]+>"),                              # HTML tags
    re.compile(r"\[[^\]]*\]"),                           # [ảnh minh họa], [video]
    re.compile(r"\([^)]*nguồn[^)]*\)", re.IGNORECASE),  # (Nguồn: VnExpress)
    re.compile(r"-{3,}|={3,}|\*{3,}"),                  # horizontal rules
    re.compile(r"\n{3,}"),                               # excessive blank lines
    re.compile(r"[ \t]{2,}"),                            # multiple spaces / tabs
]

_REPEATED_PUNCT: re.Pattern = re.compile(r"([!?.]){2,}")
_REPEATED_DOTS:  re.Pattern = re.compile(r"\.{4,}")


# ---------------------------------------------------------------------------
# Unicode-safe word boundary (works with Vietnamese diacritics)
# ---------------------------------------------------------------------------
def _vi_word_boundary(key: str) -> re.Pattern:
    """
    \b fails on Vietnamese because diacritics are non-ASCII.
    This lookaround matches 'key' only when surrounded by whitespace or
    string start / end — equivalent to \b for space-tokenised Vietnamese.
    """
    return re.compile(
        rf"(?<!\S){re.escape(key)}(?!\S)",
        re.IGNORECASE | re.UNICODE,
    )


# ---------------------------------------------------------------------------
# Stats counter
# ---------------------------------------------------------------------------
@dataclass
class _Stats:
    processed: int = field(default=0)
    skipped:   int = field(default=0)
    errors:    int = field(default=0)

    def __str__(self) -> str:
        return (
            f"Processed: {self.processed} | "
            f"Skipped/empty: {self.skipped} | "
            f"Errors: {self.errors}"
        )


# ---------------------------------------------------------------------------
# Resource loaders (module-level → importable, testable)
# ---------------------------------------------------------------------------

def load_teencode(path: str) -> list[tuple[re.Pattern, str]]:
    """
    Load teencode rules from a plain-text file.
    Format (one rule per line):  shorthand|full_form
    Comment lines starting with '#' and blank lines are ignored.
    Lines without exactly one '|' are skipped with a debug log.
    """
    if not path or not os.path.exists(path):
        logger.warning("Teencode file not found at '%s'. Skipping teencode step.", path)
        return []

    rules: list[tuple[re.Pattern, str]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", maxsplit=1)      # maxsplit=1 handles values containing '|'
            if len(parts) != 2:
                logger.debug("Skipping malformed teencode line %d: %r", lineno, line)
                continue
            key, value = parts[0].strip(), parts[1].strip()
            if not key:
                continue
            rules.append((_vi_word_boundary(key), value))

    logger.info("Loaded %d teencode rules from '%s'.", len(rules), path)
    return rules


def load_stopwords(path: str) -> set[str]:
    """Load stopwords from a one-token-per-line file (already segmented form)."""
    if not path or not os.path.exists(path):
        logger.warning("Stopword file not found at '%s'. Skipping stopword step.", path)
        return set()

    with open(path, encoding="utf-8") as fh:
        words = {line.strip().lower() for line in fh if line.strip()}

    logger.info("Loaded %d stopwords from '%s'.", len(words), path)
    return words


# ---------------------------------------------------------------------------
# Pure text-transformation helpers (module-level → picklable)
# ---------------------------------------------------------------------------

def _apply_noise_patterns(text: str) -> str:
    for pat in _NOISE_PATTERNS:
        text = pat.sub(" ", text)
    return text


def _normalize_punctuation(text: str) -> str:
    text = _REPEATED_PUNCT.sub(r"\1", text)   # !!! → !
    text = _REPEATED_DOTS.sub("...", text)     # ........ → ...
    return text


def _normalize_teencode(text: str, rules: list[tuple[re.Pattern, str]]) -> str:
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


def _segment_text(text: str) -> str:
    """
    Word-segment text with underthesea.
    Texts longer than MAX_SEGMENT_CHARS are chunked to avoid OOM / timeouts.
    This runs inside a subprocess so there are no shared-state issues.
    """
    if len(text) <= MAX_SEGMENT_CHARS:
        return word_tokenize(text, format="text")

    chunks = [
        text[i : i + MAX_SEGMENT_CHARS]
        for i in range(0, len(text), MAX_SEGMENT_CHARS)
    ]
    return " ".join(word_tokenize(chunk, format="text") for chunk in chunks)


def _remove_stopwords(segmented_text: str, stopwords: set[str]) -> str:
    """
    Drop stopwords from an already-segmented string.
    Compound tokens use underscore joints, e.g. 'sinh_viên'.
    """
    if not stopwords:
        return segmented_text
    return " ".join(
        tok for tok in segmented_text.split()
        if tok.lower() not in stopwords
    )


def _clean_and_segment(
    raw: str,
    title: str,
    teencode_rules: list[tuple[re.Pattern, str]],
    stopwords: set[str],
) -> Optional[str]:
    if not raw or not raw.strip():
        return None

    # 1. Unicode repair
    text = ftfy.fix_text(raw)

    # 2. Structural noise
    text = _apply_noise_patterns(text)

    # 3. Manual cleaning (replaces cleantext — no version issues)
    # URLs
    text = re.sub(r'https?://\S+|www\.\S+', ' ', text)
    # Emails
    text = re.sub(r'\S+@\S+\.\S+', ' ', text)
    # Phone numbers
    text = re.sub(r'(\+84|0)[0-9]{8,10}', ' ', text)
    # Currency symbols
    text = re.sub(r'[$€£¥₫₩]', ' ', text)
    # Lowercase
    text = text.lower()

    # 4. Teencode
    text = _normalize_teencode(text, teencode_rules)

    # 5. Punctuation
    text = _normalize_punctuation(text)

    # 6. Whitespace collapse
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return None

    # 7. Word segmentation
    try:
        segmented = _segment_text(text)
    except Exception as exc:
        logger.warning("word_tokenize failed for '%s': %s — using raw text", title, exc)
        segmented = text

    # 8. Stopword removal
    if stopwords:
        segmented = _remove_stopwords(segmented, stopwords)

    return segmented.strip() or None


# ---------------------------------------------------------------------------
# Worker function — module-level so ProcessPoolExecutor can pickle it
# ---------------------------------------------------------------------------

def _worker(
    doc: dict,
    teencode_rules: list[tuple[re.Pattern, str]],
    stopwords: set[str],
) -> Optional[UpdateOne]:
    """
    Process one MongoDB document through the full pipeline.
    Returns an UpdateOne operation ready for bulk_write, or None on skip/error.
    """
    doc_id = doc.get("_id")
    title  = doc.get("title", "")[:40]

    try:
        processed_content = _clean_and_segment(
            doc.get("content", ""), title, teencode_rules, stopwords
        )
        processed_summary = _clean_and_segment(
            doc.get("summary", ""), title, teencode_rules, stopwords
        )

        if not processed_content and not processed_summary:
            logger.warning("Skipping '%s' — empty after full pipeline.", title)
            return None

        return UpdateOne(
            {"_id": doc_id},
            {
                "$set": {
                    "processed_content": processed_content,
                    "processed_summary": processed_summary,
                    "is_preprocessed":   True,
                }
            },
        )

    except Exception as exc:
        logger.error("Error processing '%s' (_id=%s): %s", title, doc_id, exc)
        return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class VietnamesePreprocessor:
    """
    End-to-end Vietnamese text preprocessing for a MongoDB-backed NLP pipeline.

    Args:
        mongo_uri:        MongoDB connection string (falls back to $MONGO_URI env var).
        db_name:          Target database name.
        collection_name:  Target collection name.
        batch_size:       Documents fetched and dispatched per batch.
        max_workers:      Number of subprocess workers.
        teencode_path:    Path to teencode file  (key|value, one per line).
        stopword_path:    Path to stopword file  (one token per line).
                          Pass None to skip stopword removal entirely.
    """

    def __init__(
        self,
        mongo_uri:       Optional[str] = None,
        db_name:         str = "nlp_database",
        collection_name: str = "raw_articles",
        batch_size:      int = 50,
        max_workers:     int = 4,
        teencode_path:   str = "./teencode.txt",
        stopword_path:   Optional[str] = None,
    ) -> None:
        uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.client      = MongoClient(uri, serverSelectionTimeoutMS=5_000)
        self.db          = self.client[db_name]
        self.collection  = self.db[collection_name]
        self.batch_size  = batch_size
        self.max_workers = max_workers

        # Load external resources once in the main process.
        # They are passed by value to each subprocess (pickle-serialised).
        self._teencode_rules: list[tuple[re.Pattern, str]] = load_teencode(teencode_path)
        self._stopwords:      set[str] = load_stopwords(stopword_path) if stopword_path else set()

    # ------------------------------------------------------------------
    # Internal: flush one batch to the process pool + MongoDB
    # ------------------------------------------------------------------

    def _flush(self, batch: list[dict], stats: _Stats) -> None:
        ops: list[UpdateOne] = []

        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(_worker, doc, self._teencode_rules, self._stopwords): doc
                for doc in batch
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    logger.error("Unhandled worker exception: %s", exc)
                    stats.errors += 1
                    continue

                if result is not None:
                    ops.append(result)
                else:
                    stats.skipped += 1

        if not ops:
            return

        try:
            write_result = self.collection.bulk_write(ops, ordered=False)
            stats.processed += write_result.modified_count
        except Exception as exc:
            logger.error("bulk_write failed: %s", exc)
            stats.errors += len(ops)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, overwrite: bool = False) -> _Stats:
        """
        Preprocess all summarised articles in the collection.

        Args:
            overwrite: If True, re-process docs already marked as preprocessed.

        Returns:
            _Stats with final counts.
        """
        query: dict = {"is_summarized": True}
        if not overwrite:
            query["is_preprocessed"] = {"$ne": True}

        total = self.collection.count_documents(query)
        logger.info("Starting preprocessing for %d articles...", total)

        stats = _Stats()
        batch: list[dict] = []

        for doc in self.collection.find(query, batch_size=self.batch_size):
            batch.append(doc)
            if len(batch) >= self.batch_size:
                self._flush(batch, stats)
                logger.info(
                    "Progress: %d / %d | %s",
                    stats.processed + stats.skipped + stats.errors,
                    total,
                    stats,
                )
                batch = []

        if batch:
            self._flush(batch, stats)

        logger.info("Finished. %s", stats)
        return stats

    def run_on_text(self, text: str) -> dict:
        """
        Run the full pipeline on a plain string — for testing and debugging.
        Does not touch MongoDB.
        """
        result = _clean_and_segment(text, "run_on_text", self._teencode_rules, self._stopwords)
        return {"processed": result}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    preprocessor = VietnamesePreprocessor(
        batch_size=100,
        max_workers=4,
        teencode_path="teencode.txt",
        stopword_path="stopwords_vi.txt",   # set to None to skip
    )
    preprocessor.process()