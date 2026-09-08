"""
Unit tests for evaluation metrics (coherence and ground truth alignment).
"""
import pytest
import numpy as np
from gensim.corpora import Dictionary
from src.evaluation.coherence import compute_topic_coherence
from src.evaluation.ground_truth_alignment import evaluate_ground_truth_alignment


def test_coherence_computation():
    texts = [
        ["medical", "doctor", "hospital", "patient", "injury"],
        ["food", "water", "supply", "ration", "relief"],
        ["shelter", "tent", "house", "homeless", "building"],
        ["rescue", "team", "helicopter", "search", "survivor"]
    ]
    dictionary = Dictionary(texts)
    corpus = [dictionary.doc2bow(t) for t in texts]

    topics = [
        ["medical", "doctor", "hospital", "patient"],
        ["food", "water", "supply", "ration"]
    ]

    scores = compute_topic_coherence(
        topic_words=topics,
        texts=texts,
        dictionary=dictionary,
        corpus=corpus,
        top_n=4
    )

    assert "c_v" in scores
    assert "u_mass" in scores
    assert not np.isnan(scores["c_v"])
    assert not np.isnan(scores["u_mass"])


def test_ground_truth_alignment():
    topic_top_words = {
        "topic_0": ["medical", "doctor", "hospital", "injury", "medicine"],
        "topic_1": ["shelter", "tent", "housing", "tarpaulin", "blanket"]
    }
    doc_dominant_topics = [0, 0, 1, 1, 0, 1]
    ground_truth = [
        "medical_emergencies",
        "medical_emergencies",
        "shelter_and_housing",
        "shelter_and_housing",
        "medical_emergencies",
        "shelter_and_housing"
    ]

    results = evaluate_ground_truth_alignment(
        topic_top_words=topic_top_words,
        doc_dominant_topics=doc_dominant_topics,
        ground_truth_labels=ground_truth
    )

    assert "mean_semantic_similarity" in results
    assert "normalized_mutual_info" in results
    assert "alignment_accuracy" in results
    assert results["alignment_accuracy"] > 0.5
