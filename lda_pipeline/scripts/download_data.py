"""
Script to download and filter the 2015 Nepal earthquake dataset from Hugging Face.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.load_crisisbench import load_and_filter_crisisbench
from src.utils.io import get_logger

logger = get_logger("scripts.download_data")

if __name__ == "__main__":
    logger.info("Starting CrisisBench data acquisition...")
    df = load_and_filter_crisisbench()
    logger.info(f"Successfully acquired and filtered {len(df):,} Nepal earthquake tweets.")
