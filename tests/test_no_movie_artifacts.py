"""Regression test to guarantee no movie domain artifacts remain in the repository."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_movie_csv_files_in_data():
    """Verify no movie CSV files exist in data/."""
    movie_csv_names = [
        "movies_metadata.csv",
        "credits.csv",
        "keywords.csv",
        "links.csv",
        "ratings.csv",
        "selected_movie_ids.csv",
        "movie_dataset.csv",
    ]
    for csv_name in movie_csv_names:
        matches = list(REPO_ROOT.glob(f"data/**/{csv_name}"))
        assert len(matches) == 0, f"Found movie CSV file: {matches}"


def test_no_movie_sql_files():
    """Verify no movie SQL files exist in sql/."""
    sql_dir = REPO_ROOT / "sql"
    if sql_dir.exists():
        movie_sql_files = list(sql_dir.glob("*movie*.sql"))
        assert len(movie_sql_files) == 0, f"Found movie SQL files: {movie_sql_files}"


def test_no_movie_transform_py():
    """Verify pwa/preprocessing/movie_transform.py is deleted."""
    transform_file = REPO_ROOT / "src" / "pwa" / "preprocessing" / "movie_transform.py"
    assert not transform_file.exists(), f"movie_transform.py still exists at {transform_file}"


def test_eval_files_have_zero_movie_references():
    """Verify golden set and benchmark queries contain zero movie references."""
    eval_dir = REPO_ROOT / "src" / "pwa" / "eval"
    golden_path = eval_dir / "golden_set.json"
    benchmark_path = eval_dir / "benchmark_queries.json"

    if golden_path.exists():
        content = golden_path.read_text(encoding="utf-8").lower()
        for forbidden in ["movie", "director", "tmdb", "movielens"]:
            assert forbidden not in content, f"Golden set contains forbidden word '{forbidden}'"

    if benchmark_path.exists():
        content = benchmark_path.read_text(encoding="utf-8").lower()
        for forbidden in ["movie", "director", "tmdb", "movielens"]:
            assert forbidden not in content, f"Benchmark queries contain forbidden word '{forbidden}'"
