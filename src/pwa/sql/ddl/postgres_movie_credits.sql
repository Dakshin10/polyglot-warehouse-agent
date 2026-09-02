-- PostgreSQL Schema DDL for movie registry credits
-- Idempotent creation script

DROP TABLE IF EXISTS movie_credits;

CREATE TABLE movie_credits (
    credit_id SERIAL PRIMARY KEY,
    movie_id INTEGER NOT NULL UNIQUE,
    director_name TEXT NOT NULL,
    director_gender SMALLINT,
    lead_actor_name TEXT,
    second_actor_name TEXT,
    lead_actor_gender SMALLINT,
    cast_size INTEGER NOT NULL,
    crew_size INTEGER NOT NULL,
    producer_name TEXT
);

COMMENT ON COLUMN movie_credits.movie_id IS 'Logical reference to MySQL movie.movie_id across database engines. Cannot be enforced via PostgreSQL Foreign Key constraint.';
