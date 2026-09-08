"""
Unit tests for text cleaning and preprocessing module.
"""
import pytest
from src.data.clean_text import TextCleaner


@pytest.fixture
def cleaner():
    return TextCleaner(
        custom_stopwords=["nepal", "earthquake", "rt", "http"],
        min_token_len=3,
        max_token_len=25,
        min_phrase_count=2,
        phrase_threshold=1.0
    )


def test_clean_raw_text(cleaner):
    raw_tweet = "RT @user: Massive #Earthquake hits Kathmandu! http://t.co/xyz &amp; 1000 people need help."
    cleaned = cleaner.clean_raw_text(raw_tweet)
    
    # Check that URLs, mentions, RT, HTML entities, and numbers are removed/cleaned
    assert "http" not in cleaned
    assert "@user" not in cleaned
    assert "rt" not in cleaned.split()
    assert "&amp;" not in cleaned
    assert "&" not in cleaned
    assert "earthquake" in cleaned
    assert "kathmandu" in cleaned


def test_tokenize_and_lemmatize(cleaner):
    text = "Doctors are treating injured patients and distributing medical supplies"
    tokens = cleaner.tokenize_and_lemmatize(text)
    
    # Should lemmatize verbs/nouns: treating -> treat, patients -> patient, supplies -> supply
    assert "doctor" in tokens or "treat" in tokens
    assert "patient" in tokens
    assert "medical" in tokens
    assert "supply" in tokens


def test_custom_stopwords(cleaner):
    text = "Nepal earthquake rescue mission underway in Nepal"
    tokens = cleaner.tokenize_and_lemmatize(text)
    
    # Custom stopwords 'nepal' and 'earthquake' should be filtered out
    assert "nepal" not in tokens
    assert "earthquake" not in tokens
    assert "rescue" in tokens
    assert "mission" in tokens


def test_phrase_modeling(cleaner):
    corpus = [
        "medical supplies needed urgently",
        "distributing medical supplies to hospitals",
        "medical supplies arriving by helicopter",
        "emergency medical supplies distributed"
    ]
    transformed = cleaner.transform_corpus(corpus, fit_phrases=True)
    
    # Check if 'medical_supplies' collocation was formed
    all_tokens = [token for doc in transformed for token in doc]
    assert any("medical_supply" in t or "medical_supplies" in t for t in all_tokens)
