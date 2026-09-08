"""
Corpus builder module for generating Gensim Dictionary, BoW Matrix, and TF-IDF representations.
"""
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
from gensim.corpora import Dictionary, MmCorpus
from gensim.models import TfidfModel

from .clean_text import TextCleaner
from ..utils.io import load_config, ensure_dir, get_logger, save_pickle

logger = get_logger("data.corpus")


def build_and_save_corpus(
    config: Optional[Dict[str, Any]] = None,
    input_csv_path: Optional[str] = None
) -> Tuple[Dictionary, List[List[Tuple[int, int]]], List[List[Tuple[int, float]]], pd.DataFrame]:
    """
    Load interim filtered dataset, execute NLP cleaning pipeline, build Gensim Dictionary,
    create BoW and TF-IDF corpora, and serialize all artifacts to data/processed/.
    """
    if config is None:
        config = load_config()

    prep_cfg = config.get("preprocessing", {})
    paths_cfg = config.get("paths", {})

    if input_csv_path is None:
        input_csv_path = paths_cfg.get("interim_data_file", "data/interim/nepal_eq.csv")

    logger.info(f"Reading interim dataset from: {input_csv_path}")
    df = pd.read_csv(input_csv_path)
    logger.info(f"Loaded {len(df):,} tweets for preprocessing.")

    # Initialize TextCleaner
    cleaner = TextCleaner(
        custom_stopwords=prep_cfg.get("custom_stopwords", []),
        min_token_len=prep_cfg.get("min_token_len", 3),
        max_token_len=prep_cfg.get("max_token_len", 25),
        min_phrase_count=prep_cfg.get("min_phrase_count", 5),
        phrase_threshold=prep_cfg.get("phrase_threshold", 10.0)
    )

    # Transform all texts into phrased tokens
    docs_tokens = cleaner.transform_corpus(df["text"].tolist(), fit_phrases=True)
    df["tokens"] = docs_tokens
    df["token_count"] = df["tokens"].apply(len)

    # Filter out empty documents after preprocessing
    non_empty_mask = df["token_count"] > 0
    logger.info(f"Documents with >=1 valid token: {non_empty_mask.sum():,} / {len(df):,}")
    df_clean = df[non_empty_mask].reset_index(drop=True)
    clean_tokens = df_clean["tokens"].tolist()

    # Build Gensim Dictionary
    logger.info("Building Gensim dictionary...")
    dictionary = Dictionary(clean_tokens)
    raw_vocab_size = len(dictionary)
    logger.info(f"Initial dictionary vocabulary size: {raw_vocab_size:,} unique terms")

    # Filter extremes
    no_below = prep_cfg.get("no_below", 5)
    no_above = prep_cfg.get("no_above", 0.5)
    keep_n = prep_cfg.get("keep_n", 10000)
    dictionary.filter_extremes(no_below=no_below, no_above=no_above, keep_n=keep_n)
    dictionary.compactify()
    logger.info(f"Dictionary filtered (no_below={no_below}, no_above={no_above}, keep_n={keep_n}): {len(dictionary):,} terms remaining")

    # Build Bag-of-Words corpus
    logger.info("Generating Bag-of-Words (BoW) corpus...")
    corpus_bow = [dictionary.doc2bow(doc) for doc in clean_tokens]

    # Build TF-IDF representation
    logger.info("Generating TF-IDF model and corpus...")
    tfidf_model = TfidfModel(corpus_bow)
    corpus_tfidf = [tfidf_model[doc] for doc in corpus_bow]

    # Serialize artifacts
    dict_file = ensure_dir(paths_cfg.get("dictionary_file", "data/processed/dictionary.gensim"))
    dictionary.save(str(dict_file))
    logger.info(f"Saved Gensim dictionary to: {dict_file}")

    bow_file = ensure_dir(paths_cfg.get("corpus_bow_file", "data/processed/corpus_bow.mm"))
    MmCorpus.serialize(str(bow_file), corpus_bow)
    logger.info(f"Saved BoW corpus to: {bow_file}")

    tfidf_file = ensure_dir(paths_cfg.get("corpus_tfidf_file", "data/processed/corpus_tfidf.mm"))
    MmCorpus.serialize(str(tfidf_file), corpus_tfidf)
    logger.info(f"Saved TF-IDF corpus to: {tfidf_file}")

    tfidf_model_file = ensure_dir(paths_cfg.get("tfidf_model_file", "data/processed/tfidf_model.gensim"))
    tfidf_model.save(str(tfidf_model_file))
    logger.info(f"Saved TF-IDF model to: {tfidf_model_file}")

    processed_tokens_file = ensure_dir(paths_cfg.get("processed_tokens_file", "data/processed/nepal_eq_processed.parquet"))
    # Save tokens as parquet and CSV backup
    df_clean.to_parquet(processed_tokens_file, index=False)
    csv_backup = processed_tokens_file.with_suffix(".csv")
    df_clean.to_csv(csv_backup, index=False)
    logger.info(f"Saved processed dataset to: {processed_tokens_file}")

    return dictionary, corpus_bow, corpus_tfidf, df_clean


if __name__ == "__main__":
    build_and_save_corpus()
