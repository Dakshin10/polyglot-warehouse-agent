import hashlib
from pathlib import Path


def test_selected_movie_ids_sha256_stability(sample_sha256_file: Path):
    """Assert current selected_movie_ids.csv matches pinned SHA-256 fixture."""
    csv_path = Path("./data/out/selected_movie_ids.csv")
    if not csv_path.exists():
        return

    with open(csv_path, "rb") as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()

    expected_hash = sample_sha256_file.read_text().strip()
    assert actual_hash == expected_hash, f"Movie selection shifted! Expected {expected_hash}, got {actual_hash}"
