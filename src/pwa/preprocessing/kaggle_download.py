"""Multi-dataset Kaggle downloader for Nexora Technologies enterprise sources.

Downloads three Kaggle datasets into structured source directories:
  - tituspr/adventureworks2022-excel-format  → data/source/adventureworks/
  - olistbr/brazilian-ecommerce             → data/source/olist/
  - olistbr/marketing-funnel-olist          → data/source/olist_marketing/

Provenance, checksums, and manifests are written to data/manifests/.
Credentials are read from KAGGLE_USERNAME / KAGGLE_KEY env vars (never
committed — see .env.example).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from pwa.settings import get_settings

logger = logging.getLogger("pwa.kaggle_download")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOURCE_BASE = REPO_ROOT / "data" / "source"
MANIFEST_DIR = REPO_ROOT / "data" / "manifests"

# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

DATASETS: list[dict[str, Any]] = [
    {
        "name": "adventureworks",
        "kaggle_slug": "tituspr/adventureworks2022-excel-format",
        "source_url": "https://www.kaggle.com/datasets/tituspr/adventureworks2022-excel-format",
        "domain": "enterprise",
        "license": "Community Data License Agreement – Permissive – Version 1.0",
        "license_url": "https://cdla.dev/permissive-1-0/",
        "description": (
            "AdventureWorks 2022 in Excel format. Contains Sales, Production, "
            "Human Resources, and Purchasing schemas used as Nexora's internal ERP source."
        ),
        "local_dir": SOURCE_BASE / "adventureworks",
    },
    {
        "name": "olist",
        "kaggle_slug": "olistbr/brazilian-ecommerce",
        "source_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
        "domain": "marketplace",
        "license": "CC BY-NC-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "description": (
            "Olist Brazilian E-Commerce Public Dataset. ~100,000 orders 2016-2018. "
            "Used as Nexora's external marketplace channel source. "
            "Non-commercial use only (CC BY-NC-SA 4.0)."
        ),
        "local_dir": SOURCE_BASE / "olist",
    },
    {
        "name": "olist_marketing",
        "kaggle_slug": "olistbr/marketing-funnel-olist",
        "source_url": "https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist",
        "domain": "marketing",
        "license": "CC BY-NC-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "description": (
            "Olist Marketing Funnel Dataset. ~8,000 leads and closed deals. "
            "Connects to Brazilian E-Commerce via seller_id. "
            "Used as Nexora's marketplace marketing channel. "
            "Non-commercial use only (CC BY-NC-SA 4.0)."
        ),
        "local_dir": SOURCE_BASE / "olist_marketing",
    },
]


# ---------------------------------------------------------------------------
# Checksum utilities
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Manifest writer
# ---------------------------------------------------------------------------


def write_manifest(dataset: dict[str, Any], downloaded_files: list[Path]) -> Path:
    """Write a YAML provenance manifest for a downloaded dataset."""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    file_entries = []
    for fp in sorted(downloaded_files):
        if fp.is_file():
            file_entries.append(
                {
                    "filename": fp.name,
                    "size_bytes": fp.stat().st_size,
                    "sha256": sha256_file(fp),
                }
            )

    manifest = {
        "dataset": {
            "name": dataset["name"],
            "provider": "kaggle",
            "kaggle_slug": dataset["kaggle_slug"],
            "source_url": dataset["source_url"],
            "domain": dataset["domain"],
            "license": dataset["license"],
            "license_url": dataset["license_url"],
            "description": dataset["description"],
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "version": "snapshot",
            "synthetic_reference_data": False,
            "files": file_entries,
        }
    }

    manifest_path = MANIFEST_DIR / f"{dataset['name']}.yaml"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        yaml.dump(manifest, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Manifest written: {manifest_path}")
    return manifest_path


# ---------------------------------------------------------------------------
# File existence check
# ---------------------------------------------------------------------------


def dataset_files_present(local_dir: Path) -> list[Path]:
    """Return list of files in local_dir with non-zero size, or empty list."""
    if not local_dir.exists():
        return []
    files = [f for f in local_dir.iterdir() if f.is_file() and f.stat().st_size > 0]
    return files


# ---------------------------------------------------------------------------
# Single dataset downloader
# ---------------------------------------------------------------------------


def download_single_dataset(dataset: dict[str, Any], api: Any, force: bool = False) -> list[Path]:
    """Download one Kaggle dataset. Returns list of downloaded file paths."""
    local_dir: Path = dataset["local_dir"]
    slug: str = dataset["kaggle_slug"]
    name: str = dataset["name"]

    local_dir.mkdir(parents=True, exist_ok=True)

    existing = dataset_files_present(local_dir)
    if existing and not force:
        logger.info(f"[{name}] {len(existing)} file(s) already present in {local_dir}. Skipping download.")
        for f in existing:
            logger.info(f"  Existing: {f.name} ({f.stat().st_size:,} bytes)")
        return existing

    logger.info(f"[{name}] Downloading {slug} → {local_dir} ...")
    try:
        api.dataset_download_files(slug, path=str(local_dir), unzip=True, force=force)
        logger.info(f"[{name}] Download complete.")
    except Exception as exc:
        _handle_download_error(name, slug, exc)
        raise

    downloaded = dataset_files_present(local_dir)
    if not downloaded:
        logger.error(f"[{name}] Download reported success but no files found in {local_dir}.")
        sys.exit(1)

    for f in downloaded:
        logger.info(f"  Downloaded: {f.name} ({f.stat().st_size:,} bytes)")

    return downloaded


def _handle_download_error(name: str, slug: str, exc: Exception) -> None:
    """Log actionable guidance for common Kaggle download failures."""
    err = str(exc)
    logger.error(f"[{name}] Failed to download {slug}: {exc}")
    if "403" in err or "Forbidden" in err:
        logger.error(
            f"  Kaggle API returned 403 Forbidden for {slug}.\n"
            f"  Please accept the dataset terms in your browser:\n"
            f"  https://www.kaggle.com/datasets/{slug}\n"
            f"  Then re-run the download."
        )
    elif "401" in err or "Unauthorized" in err:
        logger.error(
            "  Kaggle API returned 401 Unauthorized.\n"
            "  Check that KAGGLE_USERNAME and KAGGLE_KEY are correctly set in .env."
        )
    elif "404" in err or "NotFound" in err:
        logger.error(f"  Kaggle dataset {slug} not found (404).\n  Verify the dataset slug is correct.")
    else:
        logger.error(
            "  Ensure KAGGLE_USERNAME and KAGGLE_KEY are set correctly in .env.\n"
            "  Docs: https://github.com/Kaggle/kaggle-api#api-credentials"
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def download_all_datasets(force: bool = False) -> bool:
    """Download all enterprise source datasets from Kaggle.

    Returns True if all datasets are present (downloaded now or previously).
    Exits with code 1 if Kaggle credentials are missing or any download fails.
    """
    settings = get_settings()

    # Inject credentials into environment (Kaggle client reads from env)
    if settings.kaggle_username:
        os.environ["KAGGLE_USERNAME"] = settings.kaggle_username
    if settings.kaggle_key:
        os.environ["KAGGLE_KEY"] = settings.kaggle_key

    if not settings.kaggle_username or not settings.kaggle_key:
        logger.error(
            "Kaggle credentials not found. Set KAGGLE_USERNAME and KAGGLE_KEY in .env.\n"
            "Get your API token from https://www.kaggle.com/settings → API → Create Token."
        )
        sys.exit(1)

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        logger.info("Kaggle API authenticated successfully.")
    except ImportError:
        logger.error("kaggle package not installed. Run: pip install kaggle")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Kaggle authentication failed: {exc}")
        sys.exit(1)

    all_success = True
    for dataset in DATASETS:
        try:
            downloaded_files = download_single_dataset(dataset, api, force=force)
            write_manifest(dataset, downloaded_files)
        except Exception:
            logger.error(f"Failed to acquire dataset: {dataset['name']}")
            all_success = False

    if all_success:
        logger.info("=== ALL ENTERPRISE DATASETS ACQUIRED SUCCESSFULLY ===")
    else:
        logger.error("One or more dataset downloads failed. Check logs above.")

    return all_success


def check_all_datasets_present() -> bool:
    """Return True if all expected source directories have non-empty files."""
    for dataset in DATASETS:
        files = dataset_files_present(dataset["local_dir"])
        if not files:
            logger.info(f"Dataset not present: {dataset['name']} ({dataset['local_dir']})")
            return False
    return True


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    force_flag = "--force" in sys.argv
    raise SystemExit(0 if download_all_datasets(force=force_flag) else 1)
