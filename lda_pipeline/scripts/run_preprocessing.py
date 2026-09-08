"""
Script to execute the preprocessing pipeline and build dictionary/corpora.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.build_corpus import build_and_save_corpus
from src.utils.io import get_logger

logger = get_logger("scripts.run_preprocessing")

if __name__ == "__main__":
    logger.info("Executing text cleaning and corpus construction pipeline...")
    dictionary, bow, tfidf, df_clean = build_and_save_corpus()
    logger.info(
        f"Corpus construction complete. {len(df_clean):,} docs, "
        f"vocabulary size: {len(dictionary):,} terms."
    )
