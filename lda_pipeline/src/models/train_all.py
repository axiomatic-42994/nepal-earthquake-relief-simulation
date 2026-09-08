"""
Orchestrator for candidate model training sweeps across K values.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from gensim.corpora import Dictionary, MmCorpus
import pandas as pd

from .train_lda_gensim import train_gensim_lda
from .train_lda_sklearn import train_sklearn_lda
from .train_nmf import train_sklearn_nmf
from ..utils.io import load_config, ensure_dir, get_logger

logger = get_logger("models.train_all")


def train_candidate_models(
    config: Optional[Dict[str, Any]] = None,
    k_values: Optional[List[int]] = None,
    candidate_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Run candidate model sweeps across specified K values and model types.
    Returns list of metadata dictionaries for all trained checkpoints.
    """
    if config is None:
        config = load_config()

    paths_cfg = config.get("paths", {})
    models_cfg = config.get("models", {})

    if k_values is None:
        k_values = models_cfg.get("k_sweep", [5, 8, 10, 12, 15, 20, 25, 30])

    if candidate_types is None:
        candidate_types = ["gensim_lda", "sklearn_lda", "sklearn_nmf"]

    checkpoints_dir = paths_cfg.get("checkpoints_dir", "models/checkpoints")
    ensure_dir(checkpoints_dir)

    # Load serialized processed data
    dict_file = paths_cfg.get("dictionary_file", "data/processed/dictionary.gensim")
    bow_file = paths_cfg.get("corpus_bow_file", "data/processed/corpus_bow.mm")
    tfidf_file = paths_cfg.get("corpus_tfidf_file", "data/processed/corpus_tfidf.mm")

    logger.info(f"Loading dictionary from {dict_file} and corpora from {bow_file} / {tfidf_file}...")
    dictionary = Dictionary.load(dict_file)
    corpus_bow = list(MmCorpus(bow_file))
    corpus_tfidf = list(MmCorpus(tfidf_file))

    logger.info(f"Starting candidate sweeps for models: {candidate_types} across K = {k_values}")
    all_metadata = []

    for k in k_values:
        logger.info(f"========== Processing K = {k} ==========")

        # 1. Gensim LDA
        if "gensim_lda" in candidate_types:
            g_cfg = models_cfg.get("gensim_lda", {})
            _, meta_g = train_gensim_lda(
                corpus=corpus_bow,
                dictionary=dictionary,
                num_topics=k,
                passes=g_cfg.get("passes", 15),
                iterations=g_cfg.get("iterations", 200),
                alpha=g_cfg.get("alpha", "auto"),
                eta=g_cfg.get("eta", "auto"),
                random_state=g_cfg.get("random_state", 42),
                checkpoint_dir=checkpoints_dir
            )
            all_metadata.append(meta_g)

        # 2. Sklearn LDA
        if "sklearn_lda" in candidate_types:
            sk_cfg = models_cfg.get("sklearn_lda", {})
            _, meta_sk = train_sklearn_lda(
                corpus=corpus_bow,
                dictionary=dictionary,
                num_topics=k,
                max_iter=sk_cfg.get("max_iter", 20),
                learning_method=sk_cfg.get("learning_method", "batch"),
                random_state=sk_cfg.get("random_state", 42),
                checkpoint_dir=checkpoints_dir
            )
            all_metadata.append(meta_sk)

        # 3. Sklearn NMF
        if "sklearn_nmf" in candidate_types:
            nmf_cfg = models_cfg.get("nmf", {})
            _, meta_nmf = train_sklearn_nmf(
                corpus_tfidf=corpus_tfidf,
                dictionary=dictionary,
                num_topics=k,
                max_iter=nmf_cfg.get("max_iter", 200),
                init=nmf_cfg.get("init", "nndsvda"),
                random_state=nmf_cfg.get("random_state", 42),
                checkpoint_dir=checkpoints_dir
            )
            all_metadata.append(meta_nmf)

    logger.info(f"All training sweeps complete. Total checkpoints generated: {len(all_metadata)}")
    return all_metadata


if __name__ == "__main__":
    train_candidate_models()
