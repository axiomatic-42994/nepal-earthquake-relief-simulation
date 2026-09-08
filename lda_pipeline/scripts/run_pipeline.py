"""
End-to-End Pipeline Runner: executes Sprints 0 through 3 seamlessly.
"""
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.load_crisisbench import load_and_filter_crisisbench
from src.data.build_corpus import build_and_save_corpus
from src.models.train_all import train_candidate_models
from src.evaluation.model_leaderboard import build_leaderboard
from src.models.select_model import select_and_package_winning_model
from src.utils.io import load_config, get_logger

logger = get_logger("pipeline")


def run_full_pipeline():
    start_time = time.time()
    config = load_config()
    paths = config.get("paths", {})

    logger.info("=" * 60)
    logger.info("🚀 STARTING END-TO-END LDA TOPIC MODELING PIPELINE (SPRINTS 0 - 3)")
    logger.info("=" * 60)

    # 1. Sprint 0: Data Acquisition
    interim_file = Path(paths.get("interim_data_file", "data/interim/nepal_eq.csv"))
    if not interim_file.exists():
        logger.info("\n--- [Sprint 0] Step 1: Downloading and Filtering CrisisBench Data ---")
        df_raw = load_and_filter_crisisbench(config=config)
    else:
        logger.info(f"\n--- [Sprint 0] Step 1: Found existing filtered data at {interim_file} ---")

    # 2. Sprint 1: Preprocessing & Corpus Construction
    dict_file = Path(paths.get("dictionary_file", "data/processed/dictionary.gensim"))
    if not dict_file.exists():
        logger.info("\n--- [Sprint 1] Step 2: Running NLP Preprocessing and Building Corpus ---")
        dictionary, bow, tfidf, df_clean = build_and_save_corpus(config=config)
    else:
        logger.info(f"\n--- [Sprint 1] Step 2: Found processed corpus at {dict_file} ---")

    # 3. Sprint 2: Candidate Model Training Sweeps
    logger.info("\n--- [Sprint 2] Step 3: Training Candidate Models Across K Sweeps ---")
    training_results = train_candidate_models(config=config)

    # 4. Sprint 3: Evaluation & Leaderboard
    logger.info("\n--- [Sprint 3] Step 4: Evaluating Models & Building Leaderboard ---")
    leaderboard_df = build_leaderboard(config=config)

    # 5. Sprint 3: Model Selection & Packaging
    logger.info("\n--- [Sprint 3] Step 5: Selecting Winner & Generating Selection Memo ---")
    selection_summary = select_and_package_winning_model(config=config)

    total_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"✅ PIPELINE EXECUTION COMPLETE in {total_time:.2f}s ({total_time / 60:.1f} mins)")
    logger.info(f"🏆 Winning Model: {selection_summary['winning_checkpoint']}")
    logger.info(f"📄 Selection Memo: {selection_summary['selection_memo_path']}")
    logger.info(f"📊 Leaderboard: {paths.get('leaderboard_file', 'reports/model_leaderboard.csv')}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_full_pipeline()
