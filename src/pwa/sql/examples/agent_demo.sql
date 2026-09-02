-- =============================================================================
-- Agent Demo Queries — 8 queries escalating from single-source to cross-engine
--
-- All queries target the mart layer only. The agent sees these views:
--   mart.v_movie            (from Aiven MySQL)
--   mart.v_movie_credits    (from Cloud SQL PostgreSQL, federated)
--   mart.v_movie_full       (cross-engine join)
--   mart.v_movie_keywords   (from CSV)
--   mart.v_integrity_exceptions (cross-engine monitor)
-- =============================================================================


-- QUERY 1: Single source (MySQL) — Genre distribution
-- Answers from v_movie alone (Aiven MySQL replicated data)
SELECT
  primary_genre,
  COUNT(*)        AS film_count,
  AVG(budget_usd) AS avg_budget,
  AVG(revenue_usd) AS avg_revenue,
  AVG(roi)        AS avg_roi
FROM `mart.v_movie`
GROUP BY primary_genre
ORDER BY film_count DESC;


-- QUERY 2: Single source (PostgreSQL) — Top directors by film count
-- Answers from v_movie_credits alone (Cloud SQL PostgreSQL federated)
SELECT
  director_name,
  COUNT(*)   AS films_directed,
  AVG(cast_size) AS avg_cast_size,
  AVG(crew_size) AS avg_crew_size
FROM `mart.v_movie_credits`
GROUP BY director_name
HAVING films_directed >= 3
ORDER BY films_directed DESC
LIMIT 15;


-- QUERY 3: Single source (CSV) — Most frequent keywords
-- Answers from v_movie_keywords alone (CSV batch load)
SELECT
  keyword,
  COUNT(DISTINCT movie_id) AS movie_count
FROM `mart.v_movie_keywords`
GROUP BY keyword
ORDER BY movie_count DESC
LIMIT 20;


-- QUERY 4: Two sources (MySQL + PostgreSQL) — Director ROI ranking
-- Requires v_movie_full which joins MySQL financials with PG credits
SELECT
  director_name,
  COUNT(*)                                            AS films,
  ROUND(APPROX_QUANTILES(roi, 2)[OFFSET(1)], 2)      AS median_roi,
  SUM(revenue_usd)                                    AS total_revenue,
  SUM(profit_usd)                                     AS total_profit
FROM `mart.v_movie_full`
GROUP BY director_name
HAVING films >= 2
ORDER BY median_roi DESC
LIMIT 10;


-- QUERY 5: Two sources (MySQL + PostgreSQL) — Lead actor box office
-- Revenue from MySQL, actor names from PostgreSQL
SELECT
  lead_actor_name,
  COUNT(*)            AS starring_roles,
  SUM(revenue_usd)    AS total_box_office,
  AVG(vote_average)   AS avg_tmdb_score,
  AVG(roi)            AS avg_roi
FROM `mart.v_movie_full`
WHERE lead_actor_name IS NOT NULL
GROUP BY lead_actor_name
HAVING starring_roles >= 3
ORDER BY total_box_office DESC
LIMIT 10;


-- QUERY 6: Three sources (MySQL + PostgreSQL + CSV ratings) — High ROI + high rated
-- Combines MySQL financials, PG credits, and MovieLens ratings
SELECT
  title,
  director_name,
  ROUND(roi, 2)     AS roi,
  profit_usd,
  vote_average       AS tmdb_score,
  avg_rating         AS movielens_score,
  rating_count       AS movielens_votes
FROM `mart.v_movie_full`
WHERE roi > 5
  AND avg_rating >= 4.0
ORDER BY roi DESC
LIMIT 15;


-- QUERY 7: All four sources — Genre + director + keywords + ratings
-- The most complex query: needs all four data sources
SELECT
  m.primary_genre,
  m.director_name,
  COUNT(DISTINCT k.keyword) AS keyword_diversity,
  AVG(m.avg_rating)         AS avg_movielens,
  AVG(m.vote_average)       AS avg_tmdb,
  SUM(m.revenue_usd)        AS total_revenue,
  ROUND(AVG(m.roi), 2)      AS avg_roi
FROM `mart.v_movie_full` m
JOIN `mart.v_movie_keywords` k USING (movie_id)
GROUP BY m.primary_genre, m.director_name
HAVING COUNT(DISTINCT m.movie_id) >= 2
ORDER BY avg_roi DESC
LIMIT 10;


-- QUERY 8: Integrity check — should return 0 rows
SELECT * FROM `mart.v_integrity_exceptions`;
