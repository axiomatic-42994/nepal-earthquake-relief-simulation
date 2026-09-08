"""
Unit tests for data loading and filtering logic.
"""
import pandas as pd
import pytest
from src.data.load_crisisbench import load_and_filter_crisisbench


def test_dataframe_filtering_logic():
    # Simulate raw DataFrame structure from HF dataset
    mock_data = {
        "id": [1, 2, 3, 4, 5],
        "event": [
            "2015_nepal_earthquake",
            "2015_nepal_earthquake",
            "2014_chile_earthquake",
            "2015_nepal_earthquake",
            "2015_nepal_earthquake"
        ],
        "lang": ["en", "en", "en", "ne", "en"],
        "text": [
            "Urgent medical supplies needed in Bhaktapur.",
            "Shelter tents distributed to survivors.",
            "Chile earthquake updates here.",
            "नेपालमा भूकम्पको क्षति",
            "Urgent medical supplies needed in Bhaktapur." # Duplicate text
        ],
        "class_label": [
            "requests_or_urgent_needs",
            "shelter_and_housing",
            "other_useful_information",
            "requests_or_urgent_needs",
            "requests_or_urgent_needs"
        ]
    }
    df = pd.DataFrame(mock_data)

    # Filter event
    df_event = df[df["event"] == "2015_nepal_earthquake"]
    assert len(df_event) == 4

    # Filter lang
    df_lang = df_event[df_event["lang"] == "en"]
    assert len(df_lang) == 3

    # Deduplicate
    df_dedup = df_lang.drop_duplicates(subset=["text"]).reset_index(drop=True)
    assert len(df_dedup) == 2
    assert "Shelter tents distributed to survivors." in df_dedup["text"].values
