-- =============================================================================
-- BigQuery Mart Layer — View and Column Descriptions
--
-- These descriptions are the ONLY context the ADK agent receives via
-- get_table_info. Every view and every column must have a description
-- stating units, provenance, and any traps.
-- =============================================================================

-- ===================== v_movie =====================

ALTER VIEW `{PROJECT}.mart.v_movie` SET OPTIONS (
  description = 'One row per movie, 1000 rows. Film financial data and metadata replicated from Aiven MySQL (movie_registry.movie). Contains budget, revenue, genre, release info, and TMDB ratings. Use v_movie_full for the complete cross-engine join.'
);

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN movie_id
  SET OPTIONS (description = 'TMDB movie identifier. Primary key. Matches movie_id in v_movie_credits and v_movie_keywords. Integer, never null.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN title
  SET OPTIONS (description = 'English display title of the film. UTF-8, may contain non-Latin characters. Never null.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN original_title
  SET OPTIONS (description = 'Title in the original language. May differ from title for non-English films.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN original_language
  SET OPTIONS (description = 'ISO 639-1 two-letter language code of the original audio track. Examples: en, fr, ja.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN release_date
  SET OPTIONS (description = 'Theatrical release date. DATE type, never null. All selected movies have a valid release date.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN release_year
  SET OPTIONS (description = 'Year extracted from release_date. Integer, useful for decade-level grouping.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN runtime_min
  SET OPTIONS (description = 'Film runtime in minutes. May be null for a small number of films where TMDB lacks data.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN budget_usd
  SET OPTIONS (description = 'Production budget in nominal USD, not inflation-adjusted. Always greater than zero — rows with unknown budgets were excluded at source. INT64, no decimal places.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN revenue_usd
  SET OPTIONS (description = 'Worldwide box office gross in nominal USD, not inflation-adjusted. Always greater than zero. INT64, no decimal places.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN roi
  SET OPTIONS (description = 'Return on investment: revenue_usd divided by budget_usd using SAFE_DIVIDE. A value of 3.0 means the film grossed three times its budget. Not a percentage. Null only if budget_usd is zero (which should not occur in this dataset).');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN profit_usd
  SET OPTIONS (description = 'Simple profit: revenue_usd minus budget_usd. Negative values indicate a box-office loss. Does not account for marketing or distribution costs.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN primary_genre
  SET OPTIONS (description = 'First genre listed in the TMDB genres array. Examples: Action, Drama, Comedy. May be null if genres were empty.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN production_country
  SET OPTIONS (description = 'ISO 3166-1 alpha-2 country code of the first listed production country. Examples: US, GB, FR.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN vote_average
  SET OPTIONS (description = 'TMDB user score on a 0-10 scale. NUMERIC type. Distinct from avg_rating which is MovieLens on a 0-5 scale. Do not compare the two directly.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN vote_count
  SET OPTIONS (description = 'Number of TMDB user votes. Used as the deterministic sort key for selecting the top 1000 movies. Integer, never null.');

ALTER VIEW `{PROJECT}.mart.v_movie` ALTER COLUMN popularity
  SET OPTIONS (description = 'TMDB popularity score. A relative metric that changes over time, higher is more popular. NUMERIC type.');


-- ===================== v_movie_credits =====================

ALTER VIEW `{PROJECT}.mart.v_movie_credits` SET OPTIONS (
  description = 'One row per movie, 1000 rows. Director and cast credits federated live from Cloud SQL PostgreSQL (movie_credits.movie_credits) via EXTERNAL_QUERY. Data is not cached — queries hit the live Postgres database. Join to v_movie on movie_id.'
);

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN movie_id
  SET OPTIONS (description = 'TMDB movie identifier. Matches movie_id in v_movie. 1:1 relationship — exactly one credits row per movie. Integer, never null, unique.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN director_name
  SET OPTIONS (description = 'Full name of the film director. First crew entry with job=Director. Never null — movies without a director were excluded at source.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN director_gender
  SET OPTIONS (description = 'TMDB gender code of the director. 0=unspecified, 1=female, 2=male. SMALLINT.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN lead_actor_name
  SET OPTIONS (description = 'Full name of the lead actor (cast order=0). May be null if cast list was empty.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN second_actor_name
  SET OPTIONS (description = 'Full name of the second-billed actor (cast order=1). May be null.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN lead_actor_gender
  SET OPTIONS (description = 'TMDB gender code of the lead actor. 0=unspecified, 1=female, 2=male.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN cast_size
  SET OPTIONS (description = 'Total number of cast members listed in TMDB credits. Integer, never null.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN crew_size
  SET OPTIONS (description = 'Total number of crew members listed in TMDB credits. Integer, never null.');

ALTER VIEW `{PROJECT}.mart.v_movie_credits` ALTER COLUMN producer_name
  SET OPTIONS (description = 'Full name of the first listed producer (crew job=Producer). May be null if no producer was listed.');


-- ===================== v_movie_full =====================

ALTER VIEW `{PROJECT}.mart.v_movie_full` SET OPTIONS (
  description = 'One row per movie, 1000 rows. Joins film financials and metadata (Aiven MySQL) with director and cast (Cloud SQL PostgreSQL federated) and MovieLens rating aggregates (CSV file). Start here for most questions. Contains columns from all three sources.'
);

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN movie_id
  SET OPTIONS (description = 'TMDB movie identifier. Primary join key across all sources. Integer, never null.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN title
  SET OPTIONS (description = 'English display title. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN original_title
  SET OPTIONS (description = 'Title in original language. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN original_language
  SET OPTIONS (description = 'ISO 639-1 language code. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN release_date
  SET OPTIONS (description = 'Theatrical release date. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN release_year
  SET OPTIONS (description = 'Year from release_date. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN runtime_min
  SET OPTIONS (description = 'Runtime in minutes. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN budget_usd
  SET OPTIONS (description = 'Production budget in nominal USD. Always > 0. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN revenue_usd
  SET OPTIONS (description = 'Worldwide box office in nominal USD. Always > 0. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN roi
  SET OPTIONS (description = 'revenue_usd / budget_usd. A value of 3.0 = 3x return. Not a percentage.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN profit_usd
  SET OPTIONS (description = 'revenue_usd - budget_usd. Negative = box office loss.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN primary_genre
  SET OPTIONS (description = 'First TMDB genre. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN production_country
  SET OPTIONS (description = 'ISO 3166-1 alpha-2 code. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN vote_average
  SET OPTIONS (description = 'TMDB score 0-10. Distinct from avg_rating (MovieLens 0-5). Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN vote_count
  SET OPTIONS (description = 'TMDB vote count. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN popularity
  SET OPTIONS (description = 'TMDB popularity score. Source: Aiven MySQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN director_name
  SET OPTIONS (description = 'Director full name. Source: Cloud SQL PostgreSQL (live federated).');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN director_gender
  SET OPTIONS (description = 'Director TMDB gender code. 0=unspecified, 1=female, 2=male. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN lead_actor_name
  SET OPTIONS (description = 'Lead actor full name. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN second_actor_name
  SET OPTIONS (description = 'Second-billed actor. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN lead_actor_gender
  SET OPTIONS (description = 'Lead actor TMDB gender code. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN cast_size
  SET OPTIONS (description = 'Total cast members. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN crew_size
  SET OPTIONS (description = 'Total crew members. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN producer_name
  SET OPTIONS (description = 'First listed producer. Source: Cloud SQL PostgreSQL.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN avg_rating
  SET OPTIONS (description = 'Mean MovieLens user rating on a 0.5-5.0 scale. Distinct from vote_average (TMDB 0-10). Source: CSV file via links.csv join.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN rating_count
  SET OPTIONS (description = 'Number of MovieLens ratings for this film. Source: CSV file.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN min_rating
  SET OPTIONS (description = 'Lowest MovieLens rating received. Scale 0.5-5.0. Source: CSV file.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN max_rating
  SET OPTIONS (description = 'Highest MovieLens rating received. Scale 0.5-5.0. Source: CSV file.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN movielens_id
  SET OPTIONS (description = 'MovieLens internal movie ID. Useful for cross-referencing with MovieLens dataset. Source: CSV file via links.csv.');

ALTER VIEW `{PROJECT}.mart.v_movie_full` ALTER COLUMN imdb_id
  SET OPTIONS (description = 'IMDb title ID (numeric part of tt-prefixed IMDb URL). Source: CSV file via links.csv.');


-- ===================== v_movie_keywords =====================

ALTER VIEW `{PROJECT}.mart.v_movie_keywords` SET OPTIONS (
  description = 'Exploded keywords: one row per movie-keyword pair. ~11,800 rows across 1000 movies. Source: CSV batch load from TMDB keywords. Join to v_movie on movie_id.'
);

ALTER VIEW `{PROJECT}.mart.v_movie_keywords` ALTER COLUMN movie_id
  SET OPTIONS (description = 'TMDB movie identifier. Matches movie_id in v_movie. Multiple rows per movie.');

ALTER VIEW `{PROJECT}.mart.v_movie_keywords` ALTER COLUMN keyword_id
  SET OPTIONS (description = 'TMDB keyword identifier. Integer.');

ALTER VIEW `{PROJECT}.mart.v_movie_keywords` ALTER COLUMN keyword
  SET OPTIONS (description = 'Keyword text in English. Examples: jealousy, toy, boy. Lowercase.');


-- ===================== v_integrity_exceptions =====================

ALTER VIEW `{PROJECT}.mart.v_integrity_exceptions` SET OPTIONS (
  description = 'Cross-engine referential integrity monitor. Should always return 0 rows if the pipeline executed correctly. issue column values: ORPHAN_CREDIT (credits row with no matching movie) or MISSING_CREDIT (movie row with no matching credits).'
);

ALTER VIEW `{PROJECT}.mart.v_integrity_exceptions` ALTER COLUMN issue
  SET OPTIONS (description = 'Type of integrity violation: ORPHAN_CREDIT or MISSING_CREDIT.');

ALTER VIEW `{PROJECT}.mart.v_integrity_exceptions` ALTER COLUMN movie_id
  SET OPTIONS (description = 'TMDB movie_id of the orphan or missing row.');

ALTER VIEW `{PROJECT}.mart.v_integrity_exceptions` ALTER COLUMN title
  SET OPTIONS (description = 'Movie title. Populated only for MISSING_CREDIT issues (from MySQL side). NULL for ORPHAN_CREDIT.');
