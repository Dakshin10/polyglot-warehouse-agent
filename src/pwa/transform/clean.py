import ast
import pandas as pd

swallowed_exceptions_count = 0


def safe_literal_eval(val):
    """Safely parse Python literal strings with ast.literal_eval."""
    global swallowed_exceptions_count
    if pd.isna(val) or not isinstance(val, str) or not val.strip():
        return []
    try:
        return ast.literal_eval(val)
    except Exception:
        swallowed_exceptions_count += 1
        return []


def extract_primary_genre(genres_list):
    """Extract primary genre name from parsed genres list."""
    if isinstance(genres_list, list) and len(genres_list) > 0 and isinstance(genres_list[0], dict):
        return str(genres_list[0].get("name", ""))[:50]
    return None


def extract_production_country(countries_list):
    """Extract primary production country iso_3166_1 code."""
    if isinstance(countries_list, list) and len(countries_list) > 0 and isinstance(countries_list[0], dict):
        code = str(countries_list[0].get("iso_3166_1", "")).upper()
        return code[:2] if len(code) >= 2 else None
    return None


def parse_credits_info(cast_parsed, crew_parsed):
    """Extract director, actors, producer, cast_size, crew_size from parsed cast and crew."""
    director_name = None
    director_gender = None
    producer_name = None
    lead_actor_name = None
    second_actor_name = None
    lead_actor_gender = None

    if isinstance(crew_parsed, list):
        for member in crew_parsed:
            if isinstance(member, dict) and member.get("job") == "Director":
                if not director_name:
                    director_name = member.get("name")
                    director_gender = member.get("gender")
            if isinstance(member, dict) and member.get("job") == "Producer":
                if not producer_name:
                    producer_name = member.get("name")

    if isinstance(cast_parsed, list):
        sorted_cast = sorted([m for m in cast_parsed if isinstance(m, dict)], key=lambda x: x.get("order", 999))
        if len(sorted_cast) > 0:
            lead_actor_name = sorted_cast[0].get("name")
            lead_actor_gender = sorted_cast[0].get("gender")
        if len(sorted_cast) > 1:
            second_actor_name = sorted_cast[1].get("name")

    cast_size = len(cast_parsed) if isinstance(cast_parsed, list) else 0
    crew_size = len(crew_parsed) if isinstance(crew_parsed, list) else 0

    return {
        "director_name": director_name,
        "director_gender": director_gender,
        "lead_actor_name": lead_actor_name,
        "second_actor_name": second_actor_name,
        "lead_actor_gender": lead_actor_gender,
        "cast_size": cast_size,
        "crew_size": crew_size,
        "producer_name": producer_name,
    }
