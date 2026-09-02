import os
import logging
from dotenv import load_dotenv
from sqlalchemy import text, types
from pwa.db import get_mysql_engine, get_pg_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load")


def load_data(mysql_df=None, pg_df=None):
    """Execute DDL scripts and load dataframes into MySQL and PostgreSQL with explicit dtypes in chunks of 200."""
    load_dotenv()

    if mysql_df is None or pg_df is None:
        from pwa.transform import transform_and_select
        mysql_df, pg_df = transform_and_select()

    logger.info("Connecting to MySQL and PostgreSQL database engines via db module...")

    mysql_engine, mysql_type = get_mysql_engine()
    pg_engine, pg_type = get_pg_engine()

    # 1. Execute MySQL DDL
    mysql_ddl_path = os.path.join(".", "sql", "mysql_schema.sql")
    if not os.path.exists(mysql_ddl_path):
        mysql_ddl_path = os.path.join(".", "src", "pwa", "sql", "ddl", "mysql_movie.sql")
    with open(mysql_ddl_path, "r", encoding="utf-8") as f:
        mysql_sql = f.read()

    logger.info(f"Executing MySQL DDL script on {mysql_type.upper()} engine...")
    with mysql_engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS movie;")
        conn.commit()

    with mysql_engine.begin() as conn:
        for statement in mysql_sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--") and not stmt.lower().startswith("drop table"):
                if mysql_type == "sqlite":
                    stmt = stmt.replace("ENGINE=InnoDB", "").replace("DEFAULT CHARSET=utf8mb4", "").replace("COLLATE=utf8mb4_unicode_ci", "")
                conn.execute(text(stmt))

    mysql_dtypes = {
        "movie_id": types.Integer(),
        "title": types.String(255),
        "original_title": types.String(255),
        "original_language": types.String(2),
        "release_date": types.Date(),
        "release_year": types.Integer(),
        "runtime_min": types.Integer(),
        "budget_usd": types.BigInteger(),
        "revenue_usd": types.BigInteger(),
        "primary_genre": types.String(50),
        "production_country": types.String(2),
        "vote_average": types.Numeric(4, 2),
        "vote_count": types.Integer(),
        "popularity": types.Numeric(10, 4),
    }

    logger.info(f"Loading {len(mysql_df)} rows into `movie` table ({mysql_type.upper()}) in chunks of 200...")
    insert_method = "multi" if mysql_type != "sqlite" else None
    mysql_df.to_sql(
        name="movie",
        con=mysql_engine,
        if_exists="append",
        index=False,
        chunksize=200,
        method=insert_method,
        dtype=mysql_dtypes
    )

    with mysql_engine.connect() as conn:
        res = conn.execute(text("SELECT COUNT(*) FROM movie")).scalar()
        logger.info(f"{mysql_type.upper()} DB reported row count for `movie`: {res}")

    # 2. Execute Postgres DDL
    pg_ddl_path = os.path.join(".", "sql", "postgres_schema.sql")
    if not os.path.exists(pg_ddl_path):
        pg_ddl_path = os.path.join(".", "src", "pwa", "sql", "ddl", "postgres_movie_credits.sql")
    with open(pg_ddl_path, "r", encoding="utf-8") as f:
        pg_sql = f.read()

    logger.info(f"Executing PostgreSQL DDL script on {pg_type.upper()} engine...")
    with pg_engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS movie_credits;")
        conn.commit()

    with pg_engine.begin() as conn:
        for statement in pg_sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--") and not stmt.startswith("COMMENT ON") and not stmt.lower().startswith("drop table"):
                if pg_type == "sqlite":
                    stmt = stmt.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                conn.execute(text(stmt))

    pg_dtypes = {
        "credit_id": types.Integer(),
        "movie_id": types.Integer(),
        "director_name": types.Text(),
        "director_gender": types.SmallInteger(),
        "lead_actor_name": types.Text(),
        "second_actor_name": types.Text(),
        "lead_actor_gender": types.SmallInteger(),
        "cast_size": types.Integer(),
        "crew_size": types.Integer(),
        "producer_name": types.Text(),
    }

    logger.info(f"Loading {len(pg_df)} rows into `movie_credits` table ({pg_type.upper()}) in chunks of 200...")
    insert_method_pg = "multi" if pg_type != "sqlite" else None
    pg_df.to_sql(
        name="movie_credits",
        con=pg_engine,
        if_exists="append",
        index=False,
        chunksize=200,
        method=insert_method_pg,
        dtype=pg_dtypes
    )

    with pg_engine.connect() as conn:
        res_pg = conn.execute(text("SELECT COUNT(*) FROM movie_credits")).scalar()
        logger.info(f"{pg_type.upper()} DB reported row count for `movie_credits`: {res_pg}")

    # Grant SELECT on movie_credits to PG_BQ_READER_USER if set
    pg_bq_user = os.getenv("PG_BQ_READER_USER", "bqreader").strip()
    if pg_type != "sqlite" and pg_bq_user:
        try:
            with pg_engine.connect() as conn:
                conn.execute(text(f"GRANT SELECT ON movie_credits TO {pg_bq_user};"))
                conn.commit()
                logger.info(f"Granted SELECT on `movie_credits` to user `{pg_bq_user}`")
        except Exception as e:
            logger.warning(f"Could not grant SELECT to {pg_bq_user}: {e}")

    logger.info("=== DATABASE LOADING COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    load_data()
