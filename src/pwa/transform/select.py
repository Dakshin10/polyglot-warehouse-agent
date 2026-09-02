import os
import logging
import pandas as pd
from .clean import safe_literal_eval, extract_primary_genre, extract_production_country, parse_credits_info, swallowed_exceptions_count

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("transform")

RAW_DIR = os.path.join(".", "data", "raw")
OUT_DIR = os.path.join(".", "data", "out")


def transform_and_select():
    """Clean data, intersect 5 sources, select top 1000 movies, and emit output CSVs."""
    os.makedirs(OUT_DIR, exist_ok=True)

    logger.info("=== ROW COUNT LEDGER & ETL INITIALIZATION ===")

    meta_raw_path = os.path.join(RAW_DIR, "movies_metadata.csv")
    credits_raw_path = os.path.join(RAW_DIR, "credits.csv")
    keywords_raw_path = os.path.join(RAW_DIR, "keywords.csv")
    links_raw_path = os.path.join(RAW_DIR, "links.csv")
    ratings_raw_path = os.path.join(RAW_DIR, "ratings_small.csv")

    meta_df = pd.read_csv(meta_raw_path, low_memory=False)
    credits_df = pd.read_csv(credits_raw_path, low_memory=False)
    keywords_df = pd.read_csv(keywords_raw_path, low_memory=False)
    links_df = pd.read_csv(links_raw_path, low_memory=False)
    ratings_df = pd.read_csv(ratings_raw_path, low_memory=False)

    logger.info(f"Raw rows count - Metadata: {len(meta_df)}, Credits: {len(credits_df)}, Keywords: {len(keywords_df)}, Links: {len(links_df)}, Ratings: {len(ratings_df)}")

    # Clean Metadata
    meta_df["movie_id"] = pd.to_numeric(meta_df["id"], errors="coerce")
    dropped_invalid_id = meta_df["movie_id"].isna().sum()
    meta_clean = meta_df.dropna(subset=["movie_id"]).copy()
    meta_clean["movie_id"] = meta_clean["movie_id"].astype(int)
    logger.info(f"Metadata dropped invalid/shifted IDs: {dropped_invalid_id}")

    meta_clean["budget"] = pd.to_numeric(meta_clean["budget"], errors="coerce").fillna(0).astype("int64")
    meta_clean["revenue"] = pd.to_numeric(meta_clean["revenue"], errors="coerce").fillna(0).astype("int64")
    meta_clean["runtime"] = pd.to_numeric(meta_clean["runtime"], errors="coerce").fillna(0).astype(int)
    meta_clean["popularity"] = pd.to_numeric(meta_clean["popularity"], errors="coerce").fillna(0.0)
    meta_clean["vote_count"] = pd.to_numeric(meta_clean["vote_count"], errors="coerce").fillna(0).astype(int)
    meta_clean["vote_average"] = pd.to_numeric(meta_clean["vote_average"], errors="coerce").fillna(0.0)

    meta_clean["release_date_dt"] = pd.to_datetime(meta_clean["release_date"], errors="coerce")
    meta_clean["release_date_str"] = meta_clean["release_date_dt"].dt.strftime("%Y-%m-%d")
    meta_clean["release_year"] = meta_clean["release_date_dt"].dt.year.fillna(0).astype(int)

    meta_clean = meta_clean.sort_values(by="vote_count", ascending=False).drop_duplicates(subset=["movie_id"], keep="first")
    logger.info(f"Cleaned Metadata rows after deduplication: {len(meta_clean)}")

    meta_clean["genres_parsed"] = meta_clean["genres"].apply(safe_literal_eval)
    meta_clean["countries_parsed"] = meta_clean["production_countries"].apply(safe_literal_eval)
    meta_clean["primary_genre"] = meta_clean["genres_parsed"].apply(extract_primary_genre)
    meta_clean["production_country"] = meta_clean["countries_parsed"].apply(extract_production_country)
    meta_clean["original_language"] = meta_clean["original_language"].fillna("").astype(str).str.strip().str[:2]

    # Clean Credits
    credits_df["movie_id"] = pd.to_numeric(credits_df["id"], errors="coerce")
    credits_clean = credits_df.dropna(subset=["movie_id"]).copy()
    credits_clean["movie_id"] = credits_clean["movie_id"].astype(int)
    credits_clean = credits_clean.drop_duplicates(subset=["movie_id"], keep="first")

    credits_clean["cast_parsed"] = credits_clean["cast"].apply(safe_literal_eval)
    credits_clean["crew_parsed"] = credits_clean["crew"].apply(safe_literal_eval)

    credits_parsed_list = []
    valid_credits_ids = set()

    for idx, row in credits_clean.iterrows():
        mid = row["movie_id"]
        c_info = parse_credits_info(row["cast_parsed"], row["crew_parsed"])
        c_info["movie_id"] = mid
        credits_parsed_list.append(c_info)

        if c_info["cast_size"] > 0 and c_info["director_name"] is not None and len(str(c_info["director_name"]).strip()) > 0:
            valid_credits_ids.add(mid)

    parsed_credits_df = pd.DataFrame(credits_parsed_list)
    logger.info(f"Credits rows with valid cast & director: {len(valid_credits_ids)}")

    # Clean Keywords
    keywords_df["movie_id"] = pd.to_numeric(keywords_df["id"], errors="coerce")
    keywords_clean = keywords_df.dropna(subset=["movie_id"]).copy()
    keywords_clean["movie_id"] = keywords_clean["movie_id"].astype(int)
    keywords_clean = keywords_clean.drop_duplicates(subset=["movie_id"], keep="first")

    keywords_clean["keywords_parsed"] = keywords_clean["keywords"].apply(safe_literal_eval)
    valid_keywords_ids = set(keywords_clean[keywords_clean["keywords_parsed"].apply(lambda x: isinstance(x, list) and len(x) > 0)]["movie_id"])
    logger.info(f"Keywords rows with non-empty keyword list: {len(valid_keywords_ids)}")

    # Clean Links & Ratings
    links_df["movie_id"] = pd.to_numeric(links_df["tmdbId"], errors="coerce")
    links_df["movielens_id"] = pd.to_numeric(links_df["movieId"], errors="coerce")
    links_clean = links_df.dropna(subset=["movie_id", "movielens_id"]).copy()
    links_clean["movie_id"] = links_clean["movie_id"].astype(int)
    links_clean["movielens_id"] = links_clean["movielens_id"].astype(int)
    links_clean = links_clean.drop_duplicates(subset=["movie_id"], keep="first")

    ratings_df["movielens_id"] = pd.to_numeric(ratings_df["movieId"], errors="coerce")
    ratings_clean = ratings_df.dropna(subset=["movielens_id"]).copy()
    ratings_clean["movielens_id"] = ratings_clean["movielens_id"].astype(int)

    ratings_joined = ratings_clean.merge(links_clean[["movielens_id", "movie_id", "imdbId"]], on="movielens_id", how="inner")

    ratings_agg = ratings_joined.groupby("movie_id").agg(
        movielens_id=("movielens_id", "first"),
        imdb_id=("imdbId", "first"),
        rating_count=("rating", "count"),
        avg_rating=("rating", "mean"),
        min_rating=("rating", "min"),
        max_rating=("rating", "max")
    ).reset_index()

    ratings_agg["avg_rating"] = ratings_agg["avg_rating"].round(4)
    ratings_agg["min_rating"] = ratings_agg["min_rating"].round(2)
    ratings_agg["max_rating"] = ratings_agg["max_rating"].round(2)

    # Intersection & Relaxation Ladder
    meta_ids = set(meta_clean["movie_id"])
    links_ids = set(links_clean["movie_id"])

    def get_candidate_ids(min_rating_count, require_budget, require_revenue):
        valid_ratings_ids = set(ratings_agg[ratings_agg["rating_count"] >= min_rating_count]["movie_id"])
        intersected = meta_ids & valid_credits_ids & valid_keywords_ids & links_ids & valid_ratings_ids
        survivors = meta_clean[meta_clean["movie_id"].isin(intersected)].copy()
        if require_budget:
            survivors = survivors[survivors["budget"] > 0]
        if require_revenue:
            survivors = survivors[survivors["revenue"] > 0]
        survivors = survivors[survivors["release_date_dt"].notna()]
        survivors = survivors[survivors["title"].notna() & (survivors["title"].str.strip() != "")]
        return survivors

    logger.info("Applying candidate selection and quality filters...")

    min_rating_threshold = 5
    req_budget = True
    req_revenue = True

    candidates = get_candidate_ids(min_rating_threshold, req_budget, req_revenue)
    logger.info(f"Candidates with default rules (rating_count >= 5, budget > 0, revenue > 0): {len(candidates)}")

    if len(candidates) < 1000:
        logger.warning(f"Only {len(candidates)} candidates found. Triggering relaxation ladder step 1: drop budget > 0 constraint.")
        req_budget = False
        candidates = get_candidate_ids(min_rating_threshold, req_budget, req_revenue)
        logger.info(f"Candidates after relaxation step 1: {len(candidates)}")

    if len(candidates) < 1000:
        logger.warning(f"Only {len(candidates)} candidates found. Triggering relaxation ladder step 2: drop revenue > 0 constraint.")
        req_revenue = False
        candidates = get_candidate_ids(min_rating_threshold, req_budget, req_revenue)
        logger.info(f"Candidates after relaxation step 2: {len(candidates)}")

    if len(candidates) < 1000:
        logger.warning(f"Only {len(candidates)} candidates found. Triggering relaxation ladder step 3: lower rating threshold to 1.")
        min_rating_threshold = 1
        candidates = get_candidate_ids(min_rating_threshold, req_budget, req_revenue)
        logger.info(f"Candidates after relaxation step 3: {len(candidates)}")

    if len(candidates) < 1000:
        logger.error(f"FATAL: Insufficient candidate movies even after relaxation ({len(candidates)} < 1000). Cannot proceed.")
        raise ValueError(f"Selection criteria yielded only {len(candidates)} rows, exactly 1,000 required.")

    selected_meta = candidates.sort_values(by=["vote_count", "movie_id"], ascending=[False, True]).head(1000).copy()

    selected_ids = list(selected_meta["movie_id"])
    logger.info(f"Selected exactly {len(selected_ids)} movies.")

    pd.DataFrame({"movie_id": selected_ids}).to_csv(os.path.join(OUT_DIR, "selected_movie_ids.csv"), index=False)
    logger.info(f"Saved {os.path.join(OUT_DIR, 'selected_movie_ids.csv')}")

    # Output 1: MySQL movie table
    mysql_movie = selected_meta[[
        "movie_id", "title", "original_title", "original_language",
        "release_date_str", "release_year", "runtime", "budget", "revenue",
        "primary_genre", "production_country", "vote_average", "vote_count", "popularity"
    ]].copy()

    mysql_movie.rename(columns={
        "release_date_str": "release_date",
        "runtime": "runtime_min",
        "budget": "budget_usd",
        "revenue": "revenue_usd"
    }, inplace=True)

    mysql_movie["release_date"] = pd.to_datetime(mysql_movie["release_date"]).dt.date

    # Output 2: PostgreSQL movie_credits table
    selected_credits = parsed_credits_df[parsed_credits_df["movie_id"].isin(selected_ids)].copy()
    selected_credits["movie_id"] = pd.Categorical(selected_credits["movie_id"], categories=selected_ids, ordered=True)
    selected_credits = selected_credits.sort_values("movie_id").reset_index(drop=True)
    selected_credits["credit_id"] = range(1, len(selected_credits) + 1)

    pg_credits = selected_credits[[
        "credit_id", "movie_id", "director_name", "director_gender",
        "lead_actor_name", "second_actor_name", "lead_actor_gender",
        "cast_size", "crew_size", "producer_name"
    ]].copy()

    pg_credits["director_gender"] = pd.to_numeric(pg_credits["director_gender"], errors="coerce").astype("Int16")
    pg_credits["lead_actor_gender"] = pd.to_numeric(pg_credits["lead_actor_gender"], errors="coerce").astype("Int16")

    # Output 3: movie_keywords.csv
    keywords_selected = keywords_clean[keywords_clean["movie_id"].isin(selected_ids)].copy()
    exploded_keywords = []

    for idx, row in keywords_selected.iterrows():
        mid = row["movie_id"]
        kw_list = row["keywords_parsed"]
        if isinstance(kw_list, list):
            for kw in kw_list:
                if isinstance(kw, dict):
                    exploded_keywords.append({
                        "movie_id": mid,
                        "keyword_id": kw.get("id"),
                        "keyword": str(kw.get("name", "")).strip()
                    })

    keywords_out_df = pd.DataFrame(exploded_keywords)
    keywords_out_df.to_csv(os.path.join(OUT_DIR, "movie_keywords.csv"), index=False)
    logger.info(f"Saved {os.path.join(OUT_DIR, 'movie_keywords.csv')} ({len(keywords_out_df)} exploded rows)")

    # Output 4: movie_ratings_agg.csv
    ratings_selected = ratings_agg[ratings_agg["movie_id"].isin(selected_ids)].copy()
    ratings_selected["movie_id"] = pd.Categorical(ratings_selected["movie_id"], categories=selected_ids, ordered=True)
    ratings_selected = ratings_selected.sort_values("movie_id").reset_index(drop=True)

    ratings_out_df = ratings_selected[[
        "movie_id", "movielens_id", "imdb_id", "rating_count", "avg_rating", "min_rating", "max_rating"
    ]].copy()

    ratings_out_df.to_csv(os.path.join(OUT_DIR, "movie_ratings_agg.csv"), index=False)
    logger.info(f"Saved {os.path.join(OUT_DIR, 'movie_ratings_agg.csv')} ({len(ratings_out_df)} rows)")

    logger.info(f"=== TRANSFORM COMPLETE. Total swallowed exceptions logged: {swallowed_exceptions_count} ===")
    return mysql_movie, pg_credits


if __name__ == "__main__":
    transform_and_select()
