import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_metadata_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "movies_metadata_sample.csv"


@pytest.fixture
def sample_credits_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "credits_sample.csv"


@pytest.fixture
def sample_sha256_file(fixtures_dir: Path) -> Path:
    return fixtures_dir / "selected_movie_ids.sha256"
