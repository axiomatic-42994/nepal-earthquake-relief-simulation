"""
Data acquisition module for downloading and filtering the Nepal earthquake subset
from the QCRI/CrisisBench-all-lang Hugging Face dataset.
"""
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
from datasets import load_dataset, concatenate_datasets

from ..utils.io import load_config, ensure_dir, get_logger

logger = get_logger("data.load")


def load_and_filter_crisisbench(
    config: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None
) -> pd.DataFrame:
    """
    Download QCRI/CrisisBench-all-lang, extract the humanitarian subset,
    filter for the 2015 Nepal earthquake English tweets, and save to interim storage.
    """
    if config is None:
        config = load_config()

    dataset_name = config.get("dataset", {}).get("hf_name", "QCRI/CrisisBench-all-lang")
    subset = config.get("dataset", {}).get("subset", "humanitarian")
    event_filter = config.get("dataset", {}).get("event_filter", "2015_nepal_earthquake")
    lang_filter = config.get("dataset", {}).get("lang_filter", "en")
    
    if output_path is None:
        output_path = config.get("paths", {}).get("interim_data_file", "data/interim/nepal_eq.csv")

    logger.info(f"Loading dataset '{dataset_name}' (subset: '{subset}')...")
    raw_dataset = load_dataset(dataset_name, subset)

    # Combine all splits (train, dev, test)
    splits = [raw_dataset[split] for split in raw_dataset.keys()]
    combined_ds = concatenate_datasets(splits)
    df = combined_ds.to_pandas()
    logger.info(f"Total rows in raw dataset across all splits: {len(df):,}")

    # Inspect events
    events_present = df["event"].unique().tolist()
    logger.info(f"Events found in dataset: {events_present}")

    # Filter event
    initial_count = len(df)
    df_filtered = df[df["event"] == event_filter].copy()
    logger.info(f"Filtered event '{event_filter}': {len(df_filtered):,} / {initial_count:,} rows")

    # Filter language if requested
    if lang_filter:
        lang_count = len(df_filtered)
        df_filtered = df_filtered[df_filtered["lang"] == lang_filter].copy()
        logger.info(f"Filtered language '{lang_filter}': {len(df_filtered):,} / {lang_count:,} rows")

    # Drop null or whitespace-only texts
    df_filtered = df_filtered.dropna(subset=["text"]).copy()
    df_filtered = df_filtered[df_filtered["text"].str.strip().str.len() > 0].copy()

    # Deduplicate based on text
    dedup_count = len(df_filtered)
    df_filtered = df_filtered.drop_duplicates(subset=["text"]).reset_index(drop=True)
    logger.info(f"After text deduplication: {len(df_filtered):,} rows (dropped {dedup_count - len(df_filtered)} duplicates)")

    # Log class_label distribution
    if "class_label" in df_filtered.columns:
        logger.info("Humanitarian class label distribution:")
        label_counts = df_filtered["class_label"].value_counts()
        for label, count in label_counts.items():
            logger.info(f"  - {label}: {count:,} ({count / len(df_filtered):.1%})")

    # Save to interim path
    out_file = ensure_dir(output_path)
    df_filtered.to_csv(out_file, index=False, encoding="utf-8")
    logger.info(f"Saved interim filtered dataset to: {out_file.resolve()}")

    return df_filtered


if __name__ == "__main__":
    load_and_filter_crisisbench()
