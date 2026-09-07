import os
import sys
import logging

from pwa.settings import get_settings

logger = logging.getLogger("pwa.kaggle_download")

RAW_DIR = os.path.join(".", "data", "raw")
EXPECTED_FILES = [
    "movies_metadata.csv",
    "credits.csv",
    "keywords.csv",
    "links.csv",
    "links_small.csv",
    "ratings_small.csv",
]


def check_raw_files_exist() -> bool:
    """Check if all expected raw files exist in ./data/raw/ and have non-zero size."""
    if not os.path.exists(RAW_DIR):
        return False
    for filename in EXPECTED_FILES:
        filepath = os.path.join(RAW_DIR, filename)
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            logger.info(f"Missing or empty file: {filepath}")
            return False
    return True


def download_dataset():
    """Download the Kaggle dataset rounakbanik/the-movies-dataset into ./data/raw/."""
    settings = get_settings()

    os.makedirs(RAW_DIR, exist_ok=True)

    if check_raw_files_exist():
        logger.info("All raw files exist and are non-empty in ./data/raw/. Skipping download.")
        for filename in EXPECTED_FILES:
            filepath = os.path.join(RAW_DIR, filename)
            logger.info(f"Existing file: {filename} ({os.path.getsize(filepath):,} bytes)")
        return

    logger.info("Downloading dataset rounakbanik/the-movies-dataset from Kaggle...")

    # The Kaggle client reads its credentials from the process environment.
    if settings.kaggle_username:
        os.environ["KAGGLE_USERNAME"] = settings.kaggle_username
    if settings.kaggle_key:
        os.environ["KAGGLE_KEY"] = settings.kaggle_key

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files("rounakbanik/the-movies-dataset", path=RAW_DIR, unzip=True)
        logger.info(f"Successfully downloaded and unzipped dataset to {RAW_DIR}")
    except Exception as e:
        logger.error(f"Failed to download dataset from Kaggle: {e}")
        if "403" in str(e) or "Forbidden" in str(e):
            logger.error(
                "Kaggle API returned HTTP 403 Forbidden. Please log in and accept the dataset terms once in your browser at: https://www.kaggle.com/datasets/rounakbanik/the-movies-dataset"
            )
        logger.error(
            "Ensure KAGGLE_USERNAME and KAGGLE_KEY are correctly set in your .env file or ~/.kaggle/kaggle.json."
        )
        sys.exit(1)

    if not check_raw_files_exist():
        logger.error("Download finished but not all expected raw files were found.")
        sys.exit(1)

    for filename in EXPECTED_FILES:
        filepath = os.path.join(RAW_DIR, filename)
        logger.info(f"Downloaded file: {filename} ({os.path.getsize(filepath):,} bytes)")


if __name__ == "__main__":
    download_dataset()
