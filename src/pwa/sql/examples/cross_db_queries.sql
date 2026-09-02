-- =============================================================================
-- CROSS-ENGINE ANALYTICAL QUERIES
--
-- These queries require combining data from both database engines:
--   1. MySQL Table: `movie` (Financials, Box Office, Genres, Popularity)
--   2. PostgreSQL Table: `movie_credits` (Directors, Actors, Crew Sizes, Producers)
--
-- In Python/Pandas or a federated query engine (such as Trino or BigQuery foreign data wrappers),
-- `movie_id` serves as the join key across engines.
-- =============================================================================

-- QUERY 1: Director Median Return-on-Investment (ROI) & Revenue Ranking
-- Requires: MySQL (revenue_usd, budget_usd) AND PostgreSQL (director_name)
SELECT 
    c.director_name,
    COUNT(m.movie_id) AS total_films,
    AVG(m.revenue_usd / m.budget_usd) AS avg_roi,
    SUM(m.revenue_usd) AS total_revenue_usd
FROM mysql_movie m
JOIN postgres_movie_credits c ON m.movie_id = c.movie_id
WHERE m.budget_usd > 0
GROUP BY c.director_name
HAVING COUNT(m.movie_id) >= 2
ORDER BY avg_roi DESC
LIMIT 10;


-- QUERY 2: Lead Actor Box Office Impact & Popularity
-- Requires: MySQL (title, revenue_usd, popularity) AND PostgreSQL (lead_actor_name)
SELECT 
    c.lead_actor_name,
    COUNT(m.movie_id) AS starring_roles,
    SUM(m.revenue_usd) AS total_box_office_usd,
    AVG(m.popularity) AS avg_popularity_score
FROM mysql_movie m
JOIN postgres_movie_credits c ON m.movie_id = c.movie_id
WHERE c.lead_actor_name IS NOT NULL
GROUP BY c.lead_actor_name
HAVING COUNT(m.movie_id) >= 2
ORDER BY total_box_office_usd DESC
LIMIT 10;


-- QUERY 3: Director Gender Diversity & Budget Allocation
-- Requires: MySQL (budget_usd, revenue_usd, vote_average) AND PostgreSQL (director_gender)
SELECT 
    CASE c.director_gender 
        WHEN 1 THEN 'Female'
        WHEN 2 THEN 'Male'
        ELSE 'Unspecified / Other'
    END AS director_gender_label,
    COUNT(m.movie_id) AS film_count,
    AVG(m.budget_usd) AS avg_budget_usd,
    AVG(m.revenue_usd) AS avg_revenue_usd,
    AVG(m.vote_average) AS avg_vote_score
FROM mysql_movie m
JOIN postgres_movie_credits c ON m.movie_id = c.movie_id
GROUP BY c.director_gender
ORDER BY film_count DESC;


-- QUERY 4: Cast Size vs. Financial Efficiency (Large Cast vs Small Cast)
-- Requires: MySQL (budget_usd, revenue_usd) AND PostgreSQL (cast_size, crew_size)
SELECT 
    CASE 
        WHEN c.cast_size < 10 THEN 'Small Cast (<10)'
        WHEN c.cast_size BETWEEN 10 AND 25 THEN 'Medium Cast (10-25)'
        ELSE 'Large Cast (>25)'
    END AS cast_tier,
    COUNT(m.movie_id) AS total_movies,
    AVG(c.crew_size) AS avg_crew_size,
    AVG(m.budget_usd) AS avg_budget_usd,
    AVG(m.revenue_usd) AS avg_revenue_usd,
    AVG(m.revenue_usd / NULLIF(m.budget_usd, 0)) AS avg_roi
FROM mysql_movie m
JOIN postgres_movie_credits c ON m.movie_id = c.movie_id
GROUP BY cast_tier
ORDER BY avg_roi DESC;


-- QUERY 5: Top Producer Portfolio & High-Rated Genre Analysis
-- Requires: MySQL (primary_genre, vote_average, vote_count) AND PostgreSQL (producer_name)
SELECT 
    c.producer_name,
    COUNT(m.movie_id) AS produced_films,
    AVG(m.vote_average) AS avg_user_rating,
    SUM(m.vote_count) AS total_votes
FROM mysql_movie m
JOIN postgres_movie_credits c ON m.movie_id = c.movie_id
WHERE c.producer_name IS NOT NULL
GROUP BY c.producer_name
HAVING COUNT(m.movie_id) >= 2
ORDER BY avg_user_rating DESC, total_votes DESC
LIMIT 10;
