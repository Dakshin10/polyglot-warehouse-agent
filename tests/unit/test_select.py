import pandas as pd


def test_intersection_logic():
    """Test 5-way intersection set math."""
    meta_ids = {1, 2, 3, 4, 5}
    credits_ids = {1, 2, 3, 4}
    keywords_ids = {1, 2, 3}
    links_ids = {1, 2, 3, 6}
    ratings_ids = {1, 2, 7}

    intersected = meta_ids & credits_ids & keywords_ids & links_ids & ratings_ids
    assert intersected == {1, 2}


def test_deterministic_sorting():
    """Sorting by vote_count descending and tie-break by movie_id ascending is deterministic."""
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
