import re
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from underthesea import word_tokenize
from cleantext import clean
from pymongo import MongoClient, UpdateOne
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

_TEENCODE_PATH = "./teencode.txt"

_NOISE_PATTERNS = [
    re.compile(r'<[^>]+>'),                         # HTML tags
    re.compile(r'\[.*?\]'),                         # bracket noise e.g. [ảnh minh họa]
    re.compile(r'\(.*?nguồn.*?\)', re.IGNORECASE),  # source attribution
    re.compile(r'---+|===+|\*\*\*+'),               # horizontal rules / separators
    re.compile(r'\n{3,}'),                          # excessive blank lines
    re.compile(r'[ \t]{2,}'),                       # multiple spaces/tabs
]

_REPEATED_PUNCT = re.compile(r'([!?.]){2,}')
_REPEATED_DOTS  = re.compile(r'\.{4,}')


class VietnamesePreprocessor:
    def __init__(
        self,
        mongo_uri: str = None,
        db_name: str = "nlp_database",
        collection_name: str = "raw_articles",
        batch_size: int = 50,
        max_workers: int = 4,
    ):
        uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5_000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.batch_size = batch_size
        self.max_workers = max_workers

        # Compile teencode patterns once
        self._teencode = self._load_teencode(_TEENCODE_PATH)

    # Load teencode
    def _load_teencode(self, path: str) -> list:
        teencode_list = []
        if not os.path.exists(path):
            logger.warning(f"Teencode file not found at {path}. Skipping teencode normalization.")
            return []

        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if '|' in line:
                    key, value = line.split('|')
                    
                    pattern = re.compile(fr'\b{key.strip()}\b', re.IGNORECASE)
                    teencode_list.append((pattern, value.strip()))
        
        logger.info(f"Loaded {len(teencode_list)} teencode rules from {path}")
        return teencode_list
    
    # ------------------------------------------------------------------
    # Text cleaning
    # ------------------------------------------------------------------

    def _apply_noise_patterns(self, text: str) -> str:
        for pattern in _NOISE_PATTERNS:
            text = pattern.sub(' ', text)
        return text

    def _normalize_punctuation(self, text: str) -> str:
        text = _REPEATED_PUNCT.sub(r'\1', text)   # !!! → !
        text = _REPEATED_DOTS.sub('...', text)    # ........ → ...
        return text

    def _normalize_teencode(self, text: str) -> str:
        for pattern, replacement in self._teencode:
            text = pattern.sub(replacement, text)
        return text

    def clean_raw_text(self, text: str) -> Optional[str]:
        """
        Full cleaning pipeline:
          1. Remove HTML / bracket noise
          2. cleantext pass (unicode fix, URL/email removal, etc.)
          3. Vietnamese-specific normalisation (teencode, punctuation)
          4. Final whitespace collapse
        """
        if not text or not text.strip():
            return None

        # Step 1 – structural noise
        text = self._apply_noise_patterns(text)

        # Step 2 – cleantext
        text = clean(
            text,
            fix_unicode=True,
            to_ascii=False,           # preserve Vietnamese diacritics
            lower=True,
            no_urls=True,
            no_emails=True,
            no_phone_numbers=True,
            no_numbers=False,         # keep numbers (important for news)
            no_digits=False,
            no_currency_symbols=True,
            replace_with_url=" ",
            lang="vi",
        )

        # Step 3 – Vietnamese normalisation
        text = self._normalize_teencode(text)
        text = self._normalize_punctuation(text)

        # Step 4 – whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text if text else None

    def _segment(self, text: str) -> Optional[str]:
        try:
            return word_tokenize(text, format="text")
        except Exception as exc:
            logger.warning("word_tokenize failed: %s", exc)
            return text  # fall back to unsegmented text

    def _process_one(self, doc: dict) -> Optional[UpdateOne]:
        doc_id = doc.get("_id")
        title  = doc.get("title", "")[:40]

        try:
            clean_content = self.clean_raw_text(doc.get("content", ""))
            clean_summary = self.clean_raw_text(doc.get("summary", ""))

            # Skip if both fields are empty after cleaning
            if not clean_content and not clean_summary:
                logger.warning("Skipping '%s' — empty after cleaning", title)
                return None

            segmented_content = self._segment(clean_content) if clean_content else None
            segmented_summary = self._segment(clean_summary) if clean_summary else None

            return UpdateOne(
                {"_id": doc_id},
                {"$set": {
                    "processed_content": segmented_content,
                    "processed_summary": segmented_summary,
                    "is_preprocessed": True,
                }},
            )

        except Exception as exc:
            logger.error("Error processing '%s' (_id=%s): %s", title, doc_id, exc)
            return None

    def process(self, overwrite: bool = False):
        """
        Process all summarised articles.

        Args:
            overwrite: If False (default), skip docs already preprocessed.
        """
        query = {"is_summarized": True}
        if not overwrite:
            query["is_preprocessed"] = {"$ne": True}

        total = self.collection.count_documents(query)
        logger.info("Starting preprocessing for %d articles...", total)

        processed = skipped = errors = 0
        cursor = self.collection.find(query, batch_size=self.batch_size)

        # Collect a batch then parallelise the CPU-bound NLP work
        batch: list = []

        def flush(batch):
            nonlocal processed, skipped, errors
            ops = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {pool.submit(self._process_one, doc): doc for doc in batch}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        ops.append(result)
                    else:
                        skipped += 1

            if ops:
                try:
                    res = self.collection.bulk_write(ops, ordered=False)
                    processed += res.modified_count
                except Exception as exc:
                    logger.error("bulk_write error: %s", exc)
                    errors += len(ops)

        for doc in cursor:
            batch.append(doc)
            if len(batch) >= self.batch_size:
                flush(batch)
                logger.info("Progress: %d / %d", processed + skipped, total)
                batch = []

        if batch:
            flush(batch)

        logger.info(
            "Done. Processed: %d | Skipped/empty: %d | Errors: %d",
            processed, skipped, errors,
        )

    def run_on_text(self, text: str) -> dict:
        cleaned   = self.clean_raw_text(text)
        segmented = self._segment(cleaned) if cleaned else None
        return {"cleaned": cleaned, "segmented": segmented}

if __name__ == "__main__":
    preprocessor = VietnamesePreprocessor(batch_size=100, max_workers=4)
    preprocessor.process()