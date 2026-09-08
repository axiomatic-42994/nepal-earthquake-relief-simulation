"""
Main Entry Point for 2015 Nepal Earthquake LDA Topic Modeling Pipeline.
Executes Sprints 0 through 3 end-to-end or individually.

Usage:
    python main.py                     # Run entire pipeline (Sprints 0 - 3)
    python main.py --sprint 0          # Sprint 0: Data Acquisition & EDA
    python main.py --sprint 1          # Sprint 1: NLP Cleaning & Corpus Construction
    python main.py --sprint 2          # Sprint 2: Candidate Models Training Sweeps
    python main.py --sprint 3          # Sprint 3: Coherence, Leaderboard & Model Selection
    python main.py --k-sweep 5 10 15   # Custom K sweep
"""
import sys
import argparse
import time
from pathlib import Path
from tabulate import tabulate

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.io import load_config, get_logger, ensure_dir
from src.data.load_crisisbench import load_and_filter_crisisbench
from src.data.build_corpus import build_and_save_corpus
from src.models.train_all import train_candidate_models
from src.evaluation.model_leaderboard import build_leaderboard
from src.models.select_model import select_and_package_winning_model

logger = get_logger("main")


def run_sprint_0(config):
    """Sprint 0: Data Acquisition & Filtering."""
    logger.info("\n" + "=" * 70)
    logger.info("📡 SPRINT 0 — DATA ACQUISITION & FILTERING")
    logger.info("=" * 70)
    df = load_and_filter_crisisbench(config=config)
    logger.info(f"✅ Sprint 0 complete. Filtered {len(df):,} tweets saved to interim dataset.")
    return df


def run_sprint_1(config):
    """Sprint 1: NLP Preprocessing & Corpus Construction."""
    logger.info("\n" + "=" * 70)
    logger.info("🧹 SPRINT 1 — PREPROCESSING & CORPUS CONSTRUCTION")
    logger.info("=" * 70)
    dictionary, bow, tfidf, df_clean = build_and_save_corpus(config=config)
    logger.info(
        f"✅ Sprint 1 complete. Vocabulary size: {len(dictionary):,} terms across {len(df_clean):,} docs."
    )
    return dictionary, bow, tfidf, df_clean


def run_sprint_2(config, k_values=None, candidate_types=None):
    """Sprint 2: Candidate Model Training Sweeps."""
    logger.info("\n" + "=" * 70)
    logger.info("⚙️ SPRINT 2 — CANDIDATE TOPIC MODEL TRAINING SWEEPS")
    logger.info("=" * 70)
    results = train_candidate_models(
        config=config,
        k_values=k_values,
        candidate_types=candidate_types
    )
    logger.info(f"✅ Sprint 2 complete. {len(results)} model checkpoints successfully saved.")
    return results


def run_sprint_3(config):
    """Sprint 3: Evaluation, Leaderboard & Model Selection."""
    logger.info("\n" + "=" * 70)
    logger.info("📊 SPRINT 3 — EVALUATION, LEADERBOARD & MODEL SELECTION")
    logger.info("=" * 70)
    
    # 1. Build Leaderboard
    leaderboard_df = build_leaderboard(config=config)
    
    # Print formatted top 5 leaderboard table to console
    top_cols = ["rank", "checkpoint_name", "model_type", "k", "coherence_c_v", "normalized_mutual_info", "alignment_macro_f1", "composite_score"]
    display_cols = [c for c in top_cols if c in leaderboard_df.columns]
    print("\n" + "=" * 40 + " MODEL LEADERBOARD (TOP RANKED) " + "=" * 40)
    print(tabulate(leaderboard_df[display_cols].head(10), headers="keys", tablefmt="grid", floatfmt=".4f"))
    print("=" * 110 + "\n")

    # 2. Select Winning Model
    selection_summary = select_and_package_winning_model(config=config)
    logger.info(f"🏆 Selected Model: {selection_summary['winning_checkpoint']}")
    logger.info(f"📄 Selection Memo: {selection_summary['selection_memo_path']}")
    logger.info("✅ Sprint 3 complete.")
    return leaderboard_df, selection_summary


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end runner for Nepal Earthquake LDA topic modeling pipeline."
    )
    parser.add_argument(
        "--sprint",
        type=int,
        choices=[0, 1, 2, 3],
        default=None,
        help="Run a specific sprint only (0, 1, 2, or 3). If omitted, runs all sprints."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to YAML configuration file."
    )
    parser.add_argument(
        "--k-sweep",
        type=int,
        nargs="+",
        default=None,
        help="Override list of K values to sweep over, e.g. --k-sweep 5 10 15 20"
    )
    parser.add_argument(
        "--candidates",
        type=str,
        nargs="+",
        default=None,
        help="Candidate model types to train, e.g. --candidates gensim_lda sklearn_lda sklearn_nmf"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    start_time = time.time()

    print("\n" + "=" * 70)
    print("  NEPAL EARTHQUAKE HUMANITARIAN NEEDS TOPIC MODELING PIPELINE")
    print("=" * 70)

    if args.sprint == 0:
        run_sprint_0(config)
    elif args.sprint == 1:
        run_sprint_1(config)
    elif args.sprint == 2:
        run_sprint_2(config, k_values=args.k_sweep, candidate_types=args.candidates)
    elif args.sprint == 3:
        run_sprint_3(config)
    else:
        # Run all sprints in sequence
        logger.info("Executing Sprints 0 through 3 in sequence...")
        
        # Sprint 0: Check or run data acquisition
        interim_csv = Path(config.get("paths", {}).get("interim_data_file", "data/interim/nepal_eq.csv"))
        if not interim_csv.exists():
            run_sprint_0(config)
        else:
            logger.info(f"Sprint 0 dataset already exists at {interim_csv}. Skipping re-download.")

        # Sprint 1: Check or run preprocessing
        dict_file = Path(config.get("paths", {}).get("dictionary_file", "data/processed/dictionary.gensim"))
        if not dict_file.exists():
            run_sprint_1(config)
        else:
            logger.info(f"Sprint 1 processed corpus already exists at {dict_file}. Proceeding.")

        # Sprint 2: Model Training Sweeps
        run_sprint_2(config, k_values=args.k_sweep, candidate_types=args.candidates)

        # Sprint 3: Evaluation, Leaderboard & Winning Model Selection
        run_sprint_3(config)

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🎉 Pipeline finished in {elapsed:.2f} seconds ({elapsed / 60:.1f} minutes).")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
