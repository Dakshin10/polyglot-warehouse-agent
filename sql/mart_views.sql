-- =============================================================================
-- BigQuery Mart Layer — Views
--
-- All downstream consumers (including the ADK natural-language agent) query
-- ONLY the mart dataset. No direct access to raw_* datasets.
--
-- Provenance:
--   raw_registry.movie        → Aiven MySQL (replicated batch)
--   raw_credits.movie_credits → Cloud SQL PostgreSQL (federated EXTERNAL_QUERY)
--   raw_files.movie_keywords  → CSV batch load
--   raw_files.movie_ratings_agg → CSV batch load
-- =============================================================================

-- v_movie: Film financials and metadata from Aiven MySQL
CREATE OR REPLACE VIEW `{PROJECT}.mart.v_movie` AS
SELECT
  movie_id,
  title,
  original_title,
  original_language,
  release_date,
  release_year,
  runtime_min,
  budget_usd,
  revenue_usd,
  SAFE_DIVIDE(revenue_usd, budget_usd) AS roi,
  revenue_usd - budget_usd             AS profit_usd,
  primary_genre,
  production_country,
  vote_average,
  vote_count,
  popularity
FROM `{PROJECT}.raw_registry.movie`;


-- v_movie_credits: Director and cast from Cloud SQL PostgreSQL (federated)
CREATE OR REPLACE VIEW `{PROJECT}.mart.v_movie_credits` AS
SELECT
  movie_id,
  director_name,
  director_gender,
  lead_actor_name,
  second_actor_name,
  lead_actor_gender,
  cast_size,
  crew_size,
  producer_name
FROM `{PROJECT}.raw_credits.movie_credits`;


-- v_movie_full: The cross-engine join. Spans Aiven MySQL and Cloud SQL PostgreSQL.
-- revenue/budget from MySQL, director/cast from PostgreSQL, ratings from CSV.
CREATE OR REPLACE VIEW `{PROJECT}.mart.v_movie_full` AS
SELECT
  m.*,
  c.director_name,
  c.director_gender,
  c.lead_actor_name,
  c.second_actor_name,
  c.lead_actor_gender,
  c.cast_size,
  c.crew_size,
  c.producer_name,
  r.avg_rating,
  r.rating_count,
  r.min_rating,
  r.max_rating,
  r.movielens_id,
  r.imdb_id
FROM `{PROJECT}.mart.v_movie` m
JOIN `{PROJECT}.mart.v_movie_credits` c USING (movie_id)
LEFT JOIN `{PROJECT}.raw_files.movie_ratings_agg` r USING (movie_id);


-- v_movie_keywords: Exploded keywords from CSV
CREATE OR REPLACE VIEW `{PROJECT}.mart.v_movie_keywords` AS
SELECT
  movie_id,
  keyword_id,
  keyword
FROM `{PROJECT}.raw_files.movie_keywords`;


-- v_integrity_exceptions: Cross-engine referential integrity monitor
CREATE OR REPLACE VIEW `{PROJECT}.mart.v_integrity_exceptions` AS
SELECT 'ORPHAN_CREDIT' AS issue, c.movie_id, CAST(NULL AS STRING) AS title
FROM `{PROJECT}.mart.v_movie_credits` c
LEFT JOIN `{PROJECT}.mart.v_movie` m USING (movie_id)
WHERE m.movie_id IS NULL
UNION ALL
SELECT 'MISSING_CREDIT', m.movie_id, m.title
FROM `{PROJECT}.mart.v_movie` m
LEFT JOIN `{PROJECT}.mart.v_movie_credits` c USING (movie_id)
WHERE c.movie_id IS NULL;
