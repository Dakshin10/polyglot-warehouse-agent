import pandas as pd
from pwa.preprocessing.movie_transform import (
    extract_primary_genre,
    extract_production_country,
    parse_credits_info,
    safe_literal_eval,
)


def test_safe_literal_eval_malformed():
    """safe_literal_eval handles malformed strings gracefully returning []."""
    assert safe_literal_eval("invalid python literal {") == []
    assert safe_literal_eval("") == []
    assert safe_literal_eval(None) == []
    assert safe_literal_eval("[{'id': 1, 'name': 'Action'}]") == [{"id": 1, "name": "Action"}]


def test_numeric_coercion_and_deduplication():
    """Numeric coercion drops string IDs and deduplication keeps highest vote_count."""
    data = pd.DataFrame(
        [
            {"id": "862", "title": "Toy Story", "vote_count": "5415", "budget": "30000000"},
            {"id": "invalid_shift", "title": "Shifted", "vote_count": "10", "budget": "0"},
            {"id": "862", "title": "Toy Story Dup", "vote_count": "100", "budget": "1000"},
        ]
    )

    data["movie_id"] = pd.to_numeric(data["id"], errors="coerce")
    clean = data.dropna(subset=["movie_id"]).copy()
    clean["movie_id"] = clean["movie_id"].astype(int)
    clean["vote_count"] = pd.to_numeric(clean["vote_count"], errors="coerce").fillna(0).astype(int)
    clean["budget"] = pd.to_numeric(clean["budget"], errors="coerce").fillna(0).astype("int64")

    # Column shift dropped
    assert len(clean) == 2
    assert "invalid_shift" not in set(clean["id"])

    # Deduplicate keeping highest vote_count
    dedup = clean.sort_values(by="vote_count", ascending=False).drop_duplicates(subset=["movie_id"], keep="first")
    assert len(dedup) == 1
    assert dedup.iloc[0]["vote_count"] == 5415
    assert dedup.iloc[0]["title"] == "Toy Story"


def test_genre_and_country_extraction():
    """Extract primary genre name and 2-letter country code."""
    genres = safe_literal_eval("[{'id': 16, 'name': 'Animation'}, {'id': 35, 'name': 'Comedy'}]")
    countries = safe_literal_eval("[{'iso_3166_1': 'US', 'name': 'United States'}]")

    assert extract_primary_genre(genres) == "Animation"
    assert extract_production_country(countries) == "US"


def test_parse_credits_info_director_and_lead_actor():
    """Director extraction picks first job=='Director', lead actor is order==0, cast_size matches."""
    cast_raw = "[{'id': 31, 'name': 'Tom Hanks', 'order': 0, 'gender': 2}, {'id': 1289, 'name': 'Tim Allen', 'order': 1, 'gender': 2}]"
    crew_raw = "[{'id': 7879, 'name': 'John Lasseter', 'job': 'Director', 'gender': 2}, {'id': 1284, 'name': 'Bonnie Arnold', 'job': 'Producer'}]"

    cast_parsed = safe_literal_eval(cast_raw)
    crew_parsed = safe_literal_eval(crew_raw)

    info = parse_credits_info(cast_parsed, crew_parsed)

    assert info["director_name"] == "John Lasseter"
    assert info["director_gender"] == 2
    assert info["lead_actor_name"] == "Tom Hanks"
    assert info["second_actor_name"] == "Tim Allen"
    assert info["producer_name"] == "Bonnie Arnold"
    assert info["cast_size"] == 2
    assert info["crew_size"] == 2
