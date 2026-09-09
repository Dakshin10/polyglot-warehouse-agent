-- MySQL Schema DDL for movie registry
-- Idempotent creation script

DROP TABLE IF EXISTS movie;

CREATE TABLE movie (
    movie_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    original_title VARCHAR(255),
    original_language CHAR(2),
    release_date DATE NOT NULL,
    release_year INT NOT NULL,
    runtime_min INT,
    budget_usd BIGINT NOT NULL,
    revenue_usd BIGINT NOT NULL,
    primary_genre VARCHAR(50),
    production_country CHAR(2),
    vote_average DECIMAL(4,2),
    vote_count INT NOT NULL,
    popularity DECIMAL(10,4),
    PRIMARY KEY (movie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    