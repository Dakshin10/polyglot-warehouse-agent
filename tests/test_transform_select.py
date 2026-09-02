import hashlib
from pathlib import Path

import pandas as pd
import pytest

SELECTED_IDS_CSV = Path("./data/out/selected_movie_ids.csv")


def test_intersection_logic():
    """The five-way intersection keeps only ids present in every source."""
    meta_ids = {1, 2, 3, 4, 5}
    credits_ids = {1, 2, 3, 4}
    keywords_ids = {1, 2, 3}
    links_ids = {1, 2, 3, 6}
    ratings_ids = {1, 2, 7}

    intersected = meta_ids & credits_ids & keywords_ids & links_ids & ratings_ids
    assert intersected == {1, 2}


def test_deterministic_sorting():
    """Sorting by vote_count descending, tie-broken by movie_id ascending, is deterministic."""
    df = pd.DataFrame(
        [
            {"movie_id": 200, "vote_count": 500},
            {"movie_id": 100, "vote_count": 500},
            {"movie_id": 300, "vote_count": 1000},
        ]
    )

    sorted_1 = df.sort_values(by=["vote_count", "movie_id"], ascending=[False, True])["movie_id"].tolist()
    sorted_2 = df.sort_values(by=["vote_count", "movie_id"], ascending=[False, True])["movie_id"].tolist()

    assert sorted_1 == [300, 100, 200]
    assert sorted_1 == sorted_2


def test_selected_movie_ids_sha256_stability(sample_sha256_file: Path):
    """The pinned hash detects selection drift: a transform tweak must not silently change which 1,000 movies we have.

    Skipped explicitly when the CSV has not been generated, rather than passing
    silently, which would be a false green.
    """
    if not SELECTED_IDS_CSV.exists():
        pytest.skip(f"{SELECTED_IDS_CSV} not generated; run `pwa source run` to produce it")

    actual_hash = hashlib.sha256(SELECTED_IDS_CSV.read_bytes()).hexdigest()
    expected_hash = sample_sha256_file.read_text().strip()
    assert actual_hash == expected_hash, f"Movie selection shifted! Expected {expected_hash}, got {actual_hash}"
