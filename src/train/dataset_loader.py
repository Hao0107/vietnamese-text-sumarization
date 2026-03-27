"""
dataset_loader.py
=================
Dataset loader for Vietnamese summarization with ViT5.
"""

from __future__ import annotations

import json
import logging
import os

from huggingface_hub import hf_hub_download
import pandas as pd
from datasets import Dataset, DatasetDict
from sklearn.model_selection import train_test_split
from transformers import T5Tokenizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class SummarizationDatasetLoader:
    def __init__(
        self,
        model_name:        str = "VietAI/vit5-base-vietnews-summarization",
        max_input_length:  int = 1024,
        max_target_length: int = 256,
        cache_dir:         str | None = "../../data/tokenized_cache",
        test_size:         float = 0.2,
        random_state:      int = 42,
        hf_token:          str | None = None,
    ) -> None:
        logger.info("Loading tokenizer: %s", model_name)
        token = hf_token or os.getenv("HF_TOKEN")
        spiece_path = hf_hub_download(
            repo_id=model_name,
            filename="spiece.model",
            token=token,
        )
        self.tokenizer = T5Tokenizer(
            vocab_file=spiece_path,
            model_max_length=max_input_length,
            use_fast=False,
            force_download=True,
        )

        self.max_input_length  = max_input_length
        self.max_target_length = max_target_length
        self.cache_dir         = cache_dir
        self.test_size         = test_size
        self.random_state      = random_state
        
    def load_from_jsonl(self, file_path: str) -> DatasetDict:
        logger.info("Loading JSONL from: %s", file_path)

        records = []
        with open(file_path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed line %d: %s", lineno, exc)

        logger.info("Loaded %d raw records.", len(records))
        return self._split(pd.DataFrame(records))

    def load_from_dataframe(self, df: pd.DataFrame) -> DatasetDict:
        logger.info("Loading from DataFrame with %d rows.", len(df))
        return self._split(df)

    def _split(self, df: pd.DataFrame) -> DatasetDict:
        df = df[["processed_content", "processed_summary"]].copy()

        before = len(df)
        df = df.dropna(subset=["processed_content", "processed_summary"])
        df = df[df["processed_content"].str.strip() != ""]
        df = df[df["processed_summary"].str.strip() != ""]
        after = len(df)
        if before != after:
            logger.warning("Dropped %d rows with None/empty text.", before - after)
        logger.info("Clean rows: %d", after)

        self._log_length_stats(df)

        train_df, temp_df = train_test_split(
            df, test_size=self.test_size, random_state=self.random_state
        )
        val_df, test_df = train_test_split(
            temp_df, test_size=0.5, random_state=self.random_state
        )

        logger.info(
            "Split -> train: %d | val: %d | test: %d",
            len(train_df), len(val_df), len(test_df),
        )

        return DatasetDict({
            "train":      Dataset.from_pandas(train_df.reset_index(drop=True)),
            "validation": Dataset.from_pandas(val_df.reset_index(drop=True)),
            "test":       Dataset.from_pandas(test_df.reset_index(drop=True)),
        })

    def _log_length_stats(self, df: pd.DataFrame) -> None:
        lengths = df["processed_content"].str.split().str.len()
        trunc   = (lengths > self.max_input_length).mean() * 100
        logger.info(
            "Content length - mean: %.0f | median: %.0f | max: %.0f | "
            "truncated (>%d): %.1f%%",
            lengths.mean(), lengths.median(), lengths.max(),
            self.max_input_length, trunc,
        )
        if trunc > 20:
            logger.warning(
                "%.1f%% of articles will be truncated. "
                "Consider vit5-large (max_input_length=1024) or chunking.", trunc
            )

    def preprocess_function(self, examples: dict) -> dict:
        model_inputs = self.tokenizer(
            examples["processed_content"],
            max_length=self.max_input_length,
            truncation=True,
        )

        labels = self.tokenizer(
            text_target=examples["processed_summary"],
            max_length=self.max_target_length,
            truncation=True,
        )

        pad_id = self.tokenizer.pad_token_id
        model_inputs["labels"] = [
            [(tok if tok != pad_id else -100) for tok in label]
            for label in labels["input_ids"]
        ]

        return model_inputs

    def get_ready_dataset(
        self,
        file_path: str | None = None,
        dataframe: pd.DataFrame | None = None,
    ) -> DatasetDict:
        if file_path is None and dataframe is None:
            raise ValueError("Provide either file_path or dataframe.")
        if file_path is not None and dataframe is not None:
            raise ValueError("Provide either file_path or dataframe, not both.")

        # Reload from cache if available
        if self.cache_dir and os.path.exists(self.cache_dir):
            logger.info("Loading tokenized dataset from cache: %s", self.cache_dir)
            return DatasetDict.load_from_disk(self.cache_dir)

        raw_datasets = (
            self.load_from_jsonl(file_path)
            if file_path is not None
            else self.load_from_dataframe(dataframe)
        )

        logger.info("Tokenizing...")
        tokenized = raw_datasets.map(
            self.preprocess_function,
            batched=True,
            remove_columns=raw_datasets["train"].column_names,
            desc="Tokenizing",
        )

        if self.cache_dir:
            logger.info("Saving tokenized dataset to: %s", self.cache_dir)
            os.makedirs(self.cache_dir, exist_ok=True)
            tokenized.save_to_disk(self.cache_dir)

        logger.info(
            "Dataset ready - train: %d | val: %d | test: %d",
            len(tokenized["train"]),
            len(tokenized["validation"]),
            len(tokenized["test"]),
        )
        return tokenized


if __name__ == "__main__":
    loader = SummarizationDatasetLoader(
        max_input_length=512,
        max_target_length=128,
        cache_dir="../../data/tokenized_cache",
    )
    dataset = loader.get_ready_dataset(file_path="")
    print("Sample keys:", list(dataset["train"][0].keys()))
    print("Train sample:", {k: v[:5] for k, v in dataset["train"][0].items()})